"""Bot de errores de precio: vigila las tiendas directamente y avisa por Telegram.

En cada búsqueda lee páginas de ofertas y categorías de cada tienda (tiendas/),
guarda el historial de precios de cada producto y avisa cuando:
  * un producto que ya conoce baja al menos un DESCUENTO_MIN % por debajo de su
    precio medio, o
  * aparece o baja un producto que todavía no tiene historial y está al menos un
    DESCUENTO_MIN_TACHADO % por debajo del precio tachado de la propia tienda.

La primera vez que lee una página solo apunta los precios, sin avisar: así no
salta con todo lo que ya estaba rebajado.

Uso:
    python3 bot.py                  # una búsqueda (lo que hace GitHub Actions)
    python3 bot.py --bucle 300      # buscar cada 5 min sin parar (VPS / Raspberry)
    python3 bot.py --prueba         # mandar un mensaje de prueba a Telegram
    python3 bot.py --simular        # buscar y enseñar los avisos sin mandarlos ni guardar nada
    python3 bot.py --tienda LDLC    # solo esa tienda (se puede repetir)
"""

import argparse
import gzip
import html
import http.client
import json
import os
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

import tiendas

NAVEGADOR = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
PAUSA_ENTRE_PAGINAS = 1.5  # segundos entre dos peticiones a la misma tienda
MAX_OBSERVACIONES = 50  # la media pesa como mucho las últimas ~50 lecturas
MIN_OBSERVACIONES = 3  # lecturas necesarias para fiarse de la media propia
BAJADA_MINIMA = 0.97  # solo cuenta si el precio cae al menos un 3 % desde la última lectura
HORAS_SIN_REPETIR = 72  # no repetir el aviso de un producto salvo que baje otro 5 %
DIAS_OLVIDO = 30  # productos y páginas que no se ven en este tiempo se borran


@dataclass
class Config:
    telegram_token: str = ""
    telegram_chat: str = ""
    descuento_min: int = 50
    descuento_min_tachado: int = 70
    precio_min: float = 30.0
    tiendas: list = field(default_factory=list)  # vacía = todas
    max_avisos: int = 15
    estado: Path = Path("estado/historial.json")

    @classmethod
    def desde_entorno(cls):
        def env(nombre, defecto=""):
            # En Actions una variable sin definir llega como cadena vacía.
            return os.environ.get(nombre) or defecto

        return cls(
            telegram_token=env("TELEGRAM_BOT_TOKEN"),
            telegram_chat=env("TELEGRAM_CHAT_ID"),
            descuento_min=int(env("DESCUENTO_MIN", "50")),
            descuento_min_tachado=int(env("DESCUENTO_MIN_TACHADO", "70")),
            precio_min=float(env("PRECIO_MIN", "30")),
            tiendas=[t.strip().lower() for t in env("TIENDAS").split(",") if t.strip()],
            max_avisos=int(env("MAX_AVISOS", "15")),
            estado=Path(env("ARCHIVO_ESTADO", "estado/historial.json")),
        )


# --- Red ---------------------------------------------------------------------

def pedir(url, datos=None):
    cabeceras = {"User-Agent": NAVEGADOR, "Accept-Language": "es-ES,es;q=0.9", "Accept-Encoding": "gzip"}
    if datos is not None:
        datos = json.dumps(datos).encode()
        cabeceras["Content-Type"] = "application/json"
    peticion = urllib.request.Request(url, data=datos, headers=cabeceras)
    try:
        with urllib.request.urlopen(peticion, timeout=30) as respuesta:
            cuerpo = respuesta.read()
    except urllib.error.HTTPError as e:
        # El mensaje no incluye la URL para no filtrar el token de Telegram en los logs.
        raise RuntimeError(f"HTTP {e.code}") from None
    except (urllib.error.URLError, http.client.HTTPException, OSError) as e:
        raise RuntimeError(f"sin respuesta ({e.__class__.__name__})") from None
    if cuerpo[:2] == b"\x1f\x8b":
        cuerpo = gzip.decompress(cuerpo)
    return cuerpo.decode("utf-8", errors="replace")


# --- Lectura de tiendas ------------------------------------------------------

@dataclass
class Lectura:
    tienda: str
    productos: list = field(default_factory=list)  # (página, Producto)
    paginas: list = field(default_factory=list)
    errores: list = field(default_factory=list)


def leer_tienda(modulo, estado_tienda, pausa=PAUSA_ENTRE_PAGINAS):
    """Lee las páginas fijas y las siguientes de la rotación. Avanza el cursor en estado_tienda."""
    lectura = Lectura(modulo.NOMBRE)
    descubiertas = []

    def leer_pagina(url):
        if lectura.paginas or lectura.errores:
            time.sleep(pausa)
        try:
            pagina = pedir(url)
        except RuntimeError as e:
            lectura.errores.append(f"{url}: {e}")
            return None
        encontrados = modulo.leer(pagina)
        if not encontrados:
            lectura.errores.append(f"{url}: 0 productos (¿ha cambiado la web?)")
        lectura.paginas.append(url)
        lectura.productos.extend((url, p) for p in encontrados)
        return pagina

    for url in modulo.FIJAS:
        pagina = leer_pagina(url)
        if pagina and hasattr(modulo, "descubrir"):
            descubiertas.extend(modulo.descubrir(pagina))

    rotar = [u for u in dict.fromkeys(modulo.ROTAR + descubiertas) if u not in modulo.FIJAS]
    if rotar:
        cursor = estado_tienda.get("cursor", 0) % len(rotar)
        cuantas = min(modulo.POR_EJECUCION, len(rotar))
        for k in range(cuantas):
            leer_pagina(rotar[(cursor + k) % len(rotar)])
        estado_tienda["cursor"] = (cursor + cuantas) % len(rotar)
    return lectura


# --- Detección ---------------------------------------------------------------

def evaluar(producto, previo, pagina_conocida, cfg):
    """Devuelve (motivo, precio de referencia) si hay que avisar, o None."""
    precio = producto.precio
    if previo and previo["n"] >= MIN_OBSERVACIONES:
        media = previo["m"]
        if (media >= cfg.precio_min and precio < previo["u"] * BAJADA_MINIMA
                and precio <= media * (1 - cfg.descuento_min / 100)):
            return "media", media
        return None
    # Sin historial suficiente: se compara con el precio tachado de la tienda.
    tachado = producto.precio_ref
    if not tachado or tachado < cfg.precio_min or precio > tachado * (1 - cfg.descuento_min_tachado / 100):
        return None
    if previo is None and not pagina_conocida:
        return None  # primera lectura de la página: ya estaba así, no es nuevo
    if previo is not None and precio >= previo["u"] * BAJADA_MINIMA:
        return None  # ya lo habíamos visto a este precio
    return "tachado", tachado


def ya_avisado(previo, precio, ahora):
    return bool(previo and previo.get("at", 0) > ahora - HORAS_SIN_REPETIR * 3600
                and precio >= previo["av"] * 0.95)


def actualizar(previo, precio, ahora):
    if previo is None:
        return {"m": precio, "n": 1, "u": precio, "t": ahora}
    n = min(previo["n"] + 1, MAX_OBSERVACIONES)
    previo.update(m=round(previo["m"] + (precio - previo["m"]) / n, 2), n=n, u=precio, t=ahora)
    return previo


# --- Avisos ------------------------------------------------------------------

def formatear_precio(euros):
    return f"{euros:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")


def descuento(precio, referencia):
    return (referencia - precio) * 100 / referencia


def mensaje(producto, motivo, referencia):
    origen = "media vista por el bot" if motivo == "media" else "precio tachado de la tienda"
    return "\n".join([
        f"🚨 <b>-{descuento(producto.precio, referencia):.0f}%</b> · {html.escape(producto.titulo[:200])}",
        "",
        f"🏪 {html.escape(producto.tienda)}",
        f"💶 Ahora: <b>{formatear_precio(producto.precio)}</b>",
        f"📊 Antes: {formatear_precio(referencia)} ({origen})",
        f"💰 Ahorro: {formatear_precio(referencia - producto.precio)}",
        f"🔗 {html.escape(producto.url)}",
    ])


def resumen_extra(avisos):
    lineas = [f"➕ <b>{len(avisos)} avisos más</b>"]
    for producto, _, referencia in avisos:
        lineas.append(f"• -{descuento(producto.precio, referencia):.0f}% {html.escape(producto.titulo[:60])} "
                      f"({html.escape(producto.tienda)}, {formatear_precio(producto.precio)}) {html.escape(producto.url)}")
    texto = "\n".join(lineas)
    return texto if len(texto) < 4000 else texto[:3990] + "…"


def enviar_telegram(cfg, texto, foto=None):
    base = f"https://api.telegram.org/bot{cfg.telegram_token}"
    if foto:
        try:
            pedir(f"{base}/sendPhoto", {"chat_id": cfg.telegram_chat, "photo": foto,
                                        "caption": texto, "parse_mode": "HTML"})
            return
        except RuntimeError:
            pass  # si Telegram no acepta la foto, se manda solo el texto
    pedir(f"{base}/sendMessage", {"chat_id": cfg.telegram_chat, "text": texto,
                                  "parse_mode": "HTML", "disable_web_page_preview": True})


# --- Estado ------------------------------------------------------------------

def cargar_estado(ruta, ahora):
    try:
        estado = json.loads(ruta.read_text())
    except (FileNotFoundError, ValueError):
        estado = {}
    limite = ahora - DIAS_OLVIDO * 86400
    return {
        "productos": {k: v for k, v in estado.get("productos", {}).items() if v.get("t", 0) >= limite},
        "paginas": {k: t for k, t in estado.get("paginas", {}).items() if t >= limite},
        "tiendas": estado.get("tiendas", {}),
    }


def guardar_estado(ruta, estado):
    ruta.parent.mkdir(parents=True, exist_ok=True)
    temporal = ruta.with_suffix(".tmp")
    temporal.write_text(json.dumps(estado, separators=(",", ":")))
    temporal.replace(ruta)


# --- Búsqueda ----------------------------------------------------------------

def ejecutar(cfg, simular=False):
    ahora = time.time()
    estado = cargar_estado(cfg.estado, ahora)
    modulos = [m for m in tiendas.TODAS if not cfg.tiendas or m.NOMBRE.lower() in cfg.tiendas]
    if not modulos:
        raise RuntimeError(f"Ninguna tienda coincide con TIENDAS={','.join(cfg.tiendas)}")

    with ThreadPoolExecutor(len(modulos)) as hilos:
        lecturas = list(hilos.map(
            lambda m: leer_tienda(m, estado["tiendas"].setdefault(m.NOMBRE, {})), modulos))

    productos = estado["productos"]
    candidatos = []
    for lectura in lecturas:
        vistos = set()
        nuevos = 0
        for pagina, producto in lectura.productos:
            if producto.clave in vistos or not producto.precio:
                continue
            vistos.add(producto.clave)
            previo = productos.get(producto.clave)
            nuevos += previo is None
            resultado = evaluar(producto, previo, simular or pagina in estado["paginas"], cfg)
            if resultado and not ya_avisado(previo, producto.precio, ahora):
                candidatos.append((producto, *resultado))
            productos[producto.clave] = actualizar(previo, producto.precio, ahora)
        for pagina in lectura.paginas:
            estado["paginas"][pagina] = ahora
        print(f"{lectura.tienda}: {len(lectura.paginas)} páginas, {len(vistos)} productos ({nuevos} nuevos)")
        for error in lectura.errores:
            print(f"  ⚠️ {error}", file=sys.stderr)

    candidatos.sort(key=lambda c: descuento(c[0].precio, c[2]), reverse=True)
    enviados = 0
    try:
        for producto, motivo, referencia in candidatos[:cfg.max_avisos]:
            texto = mensaje(producto, motivo, referencia)
            if simular:
                print("\n" + texto)
            else:
                try:
                    enviar_telegram(cfg, texto, producto.imagen)
                except RuntimeError as e:
                    print(f"No se pudo avisar de {producto.clave}: {e}", file=sys.stderr)
                    continue
                time.sleep(0.5)
            productos[producto.clave].update(av=producto.precio, at=ahora)
            enviados += 1
        sobrantes = candidatos[cfg.max_avisos:]
        if sobrantes:
            texto = resumen_extra(sobrantes)
            if simular:
                print("\n" + texto)
            else:
                try:
                    enviar_telegram(cfg, texto)
                except RuntimeError as e:
                    print(f"No se pudo mandar el resumen: {e}", file=sys.stderr)
            for producto, _, _ in sobrantes:
                productos[producto.clave].update(av=producto.precio, at=ahora)
    finally:
        if not simular:
            guardar_estado(cfg.estado, estado)

    print(f"{len(candidatos)} posibles errores de precio, {enviados} avisos {'mostrados' if simular else 'enviados'}.")
    if all(not lectura.paginas for lectura in lecturas):
        raise RuntimeError("No se pudo leer ninguna tienda.")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--bucle", type=int, metavar="SEGUNDOS", help="repetir la búsqueda cada N segundos")
    parser.add_argument("--prueba", action="store_true", help="mandar un mensaje de prueba a Telegram y salir")
    parser.add_argument("--simular", action="store_true", help="enseñar los avisos sin mandarlos ni guardar nada")
    parser.add_argument("--tienda", action="append", default=[], help="buscar solo en esta tienda")
    args = parser.parse_args()

    cfg = Config.desde_entorno()
    if args.tienda:
        cfg.tiendas = [t.lower() for t in args.tienda]
    if not args.simular:
        faltan = [n for n, v in [("TELEGRAM_BOT_TOKEN", cfg.telegram_token),
                                 ("TELEGRAM_CHAT_ID", cfg.telegram_chat)] if not v]
        if faltan:
            sys.exit(f"Faltan variables de entorno: {', '.join(faltan)}")

    if args.prueba:
        enviar_telegram(cfg, "✅ Bot de errores de precio configurado correctamente.")
        print("Mensaje de prueba enviado.")
        return

    while True:
        try:
            ejecutar(cfg, simular=args.simular)
        except RuntimeError as e:
            if not args.bucle:
                sys.exit(str(e))
            print(e, file=sys.stderr)
        if not args.bucle:
            break
        time.sleep(args.bucle)


if __name__ == "__main__":
    main()
