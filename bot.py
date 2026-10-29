"""Bot de errores de precio (gratis, sin API de pago).

Lee las ofertas más nuevas de Chollometro, que para cada una publica el precio
actual y el precio habitual del producto, y avisa por Telegram de las que están
al menos un DESCUENTO_MIN % por debajo, o que alguien ha marcado como
"error de precio" en el título. Cubre Amazon y el resto de tiendas.

Uso:
    python3 bot.py                 # una búsqueda (lo que hace GitHub Actions)
    python3 bot.py --bucle 300     # buscar cada 5 min sin parar (VPS / Raspberry)
    python3 bot.py --prueba        # mandar un mensaje de prueba a Telegram
"""

import argparse
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

LISTADO_URL = "https://www.chollometro.com/nuevos?page={}"
OFERTA_URL = "https://www.chollometro.com/ofertas/{}-{}"
IMAGEN_URL = "https://static.chollometro.com/{path}/{name}/re/300x300/qt/60/{name}.jpg"
NAVEGADOR = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
ERROR_EN_TITULO = re.compile(r"error\s+de\s+precio|precio\s+err[oó]neo|\bbug\b", re.IGNORECASE)
DIAS_MEMORIA = 7  # tras esto se olvida qué ofertas ya se avisaron


@dataclass
class Config:
    telegram_token: str
    telegram_chat: str
    descuento_min: int = 50
    precio_min: float = 1.0
    tiendas: list = field(default_factory=list)  # vacía = todas
    paginas: int = 2
    max_avisos: int = 15
    estado: Path = Path("estado/vistos.json")

    @classmethod
    def desde_entorno(cls):
        def env(nombre, defecto=""):
            # En Actions una variable sin definir llega como cadena vacía.
            return os.environ.get(nombre) or defecto

        return cls(
            telegram_token=env("TELEGRAM_BOT_TOKEN"),
            telegram_chat=env("TELEGRAM_CHAT_ID"),
            descuento_min=int(env("DESCUENTO_MIN", "50")),
            precio_min=float(env("PRECIO_MIN", "1")),
            tiendas=[t.strip().lower() for t in env("TIENDAS").split(",") if t.strip()],
            paginas=int(env("PAGINAS", "2")),
            max_avisos=int(env("MAX_AVISOS", "15")),
            estado=Path(env("ARCHIVO_ESTADO", "estado/vistos.json")),
        )


def _pedir(url, datos=None):
    cabeceras = {"User-Agent": NAVEGADOR, "Accept-Language": "es-ES,es;q=0.9"}
    if datos is not None:
        datos = json.dumps(datos).encode()
        cabeceras["Content-Type"] = "application/json"
    peticion = urllib.request.Request(url, data=datos, headers=cabeceras)
    try:
        with urllib.request.urlopen(peticion, timeout=30) as respuesta:
            return respuesta.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        # El mensaje no incluye la URL para no filtrar el token de Telegram en los logs.
        raise RuntimeError(f"HTTP {e.code}: {e.read()[:300].decode(errors='replace')}") from None
    except urllib.error.URLError as e:
        raise RuntimeError(f"Sin conexión: {e.reason}") from None


def extraer_ofertas(pagina_html):
    """Saca los objetos JSON de cada oferta que Chollometro incrusta en el HTML."""
    decodificador = json.JSONDecoder()
    ofertas = {}
    i = 0
    while (i := pagina_html.find('{"threadId":', i)) != -1:
        try:
            oferta, fin = decodificador.raw_decode(pagina_html, i)
        except ValueError:
            i += 1
            continue
        if "price" in oferta and "title" in oferta:
            ofertas[oferta["threadId"]] = oferta
        i = fin
    return list(ofertas.values())


def buscar_ofertas(cfg):
    ofertas = []
    for pagina in range(1, cfg.paginas + 1):
        try:
            ofertas.extend(extraer_ofertas(_pedir(LISTADO_URL.format(pagina))))
        except RuntimeError as e:
            raise RuntimeError(f"Error leyendo Chollometro: {e}") from None
    if not ofertas:
        raise RuntimeError("Chollometro no devolvió ofertas: puede que haya cambiado su web.")
    return ofertas


def tienda(oferta):
    return (oferta.get("merchant") or {}).get("merchantName") or oferta.get("linkHost") or "?"


def descuento(oferta):
    """Porcentaje por debajo del precio habitual, o None si no se conoce."""
    precio, habitual = oferta.get("price") or 0, oferta.get("nextBestPrice") or 0
    if precio <= 0 or habitual <= precio:
        return None
    return (habitual - precio) * 100 / habitual


def es_chollo(oferta, cfg):
    if oferta.get("isExpired") or oferta.get("isLocal") or oferta.get("type") != "Deal":
        return False
    if cfg.tiendas and not any(t in tienda(oferta).lower() for t in cfg.tiendas):
        return False
    if (oferta.get("price") or 0) < cfg.precio_min:
        return False
    pct = descuento(oferta)
    return (pct is not None and pct >= cfg.descuento_min) or bool(ERROR_EN_TITULO.search(oferta["title"]))


def formatear_precio(euros):
    return f"{euros:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")


def enlace(oferta):
    return OFERTA_URL.format(oferta.get("titleSlug") or "oferta", oferta["threadId"])


def imagen(oferta):
    img = oferta.get("mainImage") or {}
    if not img.get("path") or not img.get("name"):
        return None
    return IMAGEN_URL.format(path=img["path"], name=img["name"])


def mensaje(oferta):
    pct = descuento(oferta)
    cabecera = f"-{pct:.0f}%" if pct else "ERROR DE PRECIO"
    lineas = [
        f"🚨 <b>{cabecera}</b> · {html.escape(oferta['title'][:200])}",
        "",
        f"💶 Ahora: <b>{formatear_precio(oferta['price'])}</b> en {html.escape(tienda(oferta))}",
    ]
    if pct:
        lineas.append(f"📊 Precio habitual: {formatear_precio(oferta['nextBestPrice'])}")
    lineas.append(f"🔗 {enlace(oferta)}")
    return "\n".join(lineas)


def enviar_telegram(cfg, texto, foto=None):
    base = f"https://api.telegram.org/bot{cfg.telegram_token}"
    if foto:
        try:
            _pedir(f"{base}/sendPhoto", {
                "chat_id": cfg.telegram_chat, "photo": foto,
                "caption": texto, "parse_mode": "HTML",
            })
            return
        except RuntimeError:
            pass  # si Telegram no acepta la foto, se manda solo el texto
    _pedir(f"{base}/sendMessage", {
        "chat_id": cfg.telegram_chat, "text": texto, "parse_mode": "HTML",
    })


def cargar_estado(ruta, ahora):
    try:
        estado = json.loads(ruta.read_text())
    except (FileNotFoundError, ValueError):
        return {}
    limite = ahora - DIAS_MEMORIA * 86400
    return {clave: ts for clave, ts in estado.items() if ts >= limite}


def guardar_estado(ruta, estado):
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(estado, indent=1, sort_keys=True))


def chollos_nuevos(ofertas, estado, cfg):
    nuevos = [o for o in ofertas if es_chollo(o, cfg) and str(o["threadId"]) not in estado]
    # Primero los marcados como error en el título, luego por descuento.
    return sorted(nuevos, key=lambda o: (bool(ERROR_EN_TITULO.search(o["title"])), descuento(o) or 0), reverse=True)


def ejecutar(cfg):
    ahora = time.time()
    estado = cargar_estado(cfg.estado, ahora)
    ofertas = buscar_ofertas(cfg)
    nuevos = chollos_nuevos(ofertas, estado, cfg)

    enviados = 0
    try:
        # Los que pasen de max_avisos no se marcan y salen en la siguiente búsqueda.
        for oferta in nuevos[:cfg.max_avisos]:
            try:
                enviar_telegram(cfg, mensaje(oferta), imagen(oferta))
            except RuntimeError as e:
                print(f"No se pudo avisar de la oferta {oferta['threadId']}: {e}", file=sys.stderr)
                continue
            estado[str(oferta["threadId"])] = ahora
            enviados += 1
    finally:
        guardar_estado(cfg.estado, estado)

    print(f"{len(ofertas)} ofertas revisadas, {len(nuevos)} chollos nuevos, {enviados} avisos enviados.")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--bucle", type=int, metavar="SEGUNDOS", help="repetir la búsqueda cada N segundos")
    parser.add_argument("--prueba", action="store_true", help="mandar un mensaje de prueba a Telegram y salir")
    args = parser.parse_args()

    cfg = Config.desde_entorno()
    faltan = [n for n, v in [("TELEGRAM_BOT_TOKEN", cfg.telegram_token), ("TELEGRAM_CHAT_ID", cfg.telegram_chat)] if not v]
    if faltan:
        sys.exit(f"Faltan variables de entorno: {', '.join(faltan)}")

    if args.prueba:
        enviar_telegram(cfg, "✅ Bot de errores de precio configurado correctamente.")
        print("Mensaje de prueba enviado.")
        return

    while True:
        try:
            ejecutar(cfg)
        except RuntimeError as e:
            if not args.bucle:
                sys.exit(str(e))
            print(e, file=sys.stderr)
        if not args.bucle:
            break
        time.sleep(args.bucle)


if __name__ == "__main__":
    main()
