"""Bot de errores de precio: vigila las tiendas directamente y avisa por Telegram.

En cada búsqueda lee páginas de ofertas y categorías de cada tienda (tiendas/),
guarda el historial de precios de cada producto y avisa cuando un producto baja
al menos un DESCUENTO_MIN % por debajo de su precio medio de los últimos 99 días.
El precio tachado que enseña la tienda no cuenta: solo el historial propio.

Ignora los productos que no compensa revender: ropa, muebles y otros
voluminosos, reacondicionados o usados, y los que de media valen menos de
PRECIO_MIN.

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
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

import tiendas

NAVEGADOR = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
PAUSA_ENTRE_PAGINAS = 1.5  # segundos entre dos peticiones a la misma tienda
DIAS_MEDIA = 99  # periodo de la media de precio
BAJADA_MINIMA = 0.97  # solo cuenta si el precio cae al menos un 3 % desde la última lectura
HORAS_SIN_REPETIR = 72  # no repetir el aviso de un producto salvo que baje otro 5 %
DIAS_OLVIDO = 30  # productos que no se ven en este tiempo se borran

# Productos que no compensa revender. Se comparan sin tildes ni mayúsculas.
EXCLUIDOS = [
    # ropa y calzado
    r"camisetas?", r"camisas?", r"pantalon(es)?", r"chaquetas?", r"abrigos?", r"sudaderas?", r"jerseys?",
    r"vestidos?", r"faldas?", r"leggings?", r"calcetines", r"pijamas?", r"banadores?", r"sujetador(es)?",
    r"calzoncillos?", r"bragas?", r"chalecos?", r"cazadoras?", r"parkas?", r"blusas?", r"chandal",
    r"bufandas?", r"gorros?", r"zapatillas de (casa|estar por casa)", r"ropa",
    # muebles y voluminosos
    r"sofas?", r"sillon(es)?", r"armarios?", r"comodas?", r"colchon(es)?", r"canapes?", r"somier",
    r"literas?", r"cabeceros?", r"estanterias?", r"aparador(es)?", r"zapateros?", r"recibidor(es)?",
    r"chaise longue", r"mesa (de )?(comedor|centro|auxiliar|escritorio|noche|jardin)", r"mesitas?",
    r"escritorios?", r"sillas?",
    # reacondicionados y usados
    r"reacondicionad[oa]s?", r"renovad[oa]s?", r"segunda mano", r"usad[oa]s?", r"open ?box",
]


def sin_tildes(texto):
    return "".join(c for c in unicodedata.normalize("NFD", texto.lower()) if unicodedata.category(c) != "Mn")


@dataclass
class Config:
    telegram_token: str = ""
    telegram_chat: str = ""
    descuento_min: int = 50
    precio_min: float = 30.0
    horas_min_historial: int = 24
    tiendas: list = field(default_factory=list)  # vacía = todas
    excluir: list = field(default_factory=list)  # palabras extra a ignorar
    max_avisos: int = 15
    estado: Path = Path("estado/historial99.json")

    @classmethod
    def desde_entorno(cls):
        def env(nombre, defecto=""):
            # En Actions una variable sin definir llega como cadena vacía.
            return os.environ.get(nombre) or defecto

        def lista(nombre):
            return [t.strip().lower() for t in env(nombre).split(",") if t.strip()]

        return cls(
            telegram_token=env("TELEGRAM_BOT_TOKEN"),
            telegram_chat=env("TELEGRAM_CHAT_ID"),
            descuento_min=int(env("DESCUENTO_MIN", "50")),
            precio_min=float(env("PRECIO_MIN", "30")),
            horas_min_historial=int(env("HORAS_MIN_HISTORIAL", "24")),
            tiendas=lista("TIENDAS"),
            excluir=lista("EXCLUIR"),
            max_avisos=int(env("MAX_AVISOS", "15")),
            estado=Path(env("ARCHIVO_ESTADO", "estado/historial99.json")),
        )

    def patron_excluidos(self):
        palabras = EXCLUIDOS + [re.escape(sin_tildes(p)) for p in self.excluir]
        return re.compile(r"\b(" + "|".join(palabras) + r")\b")


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
    productos: list = field(default_factory=list)
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
        lectura.productos.extend(encontrados)
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


# --- Historial y detección ---------------------------------------------------

def media_periodo(historial, ahora):
    """Precio medio ponderado por tiempo en los últimos DIAS_MEDIA días (o desde que se conoce)."""
    inicio = max(historial["p0"], ahora - DIAS_MEDIA * 86400)
    if ahora <= inicio:
        return None
    puntos = historial["h"]
    total = 0.0
    for i, (desde, precio) in enumerate(puntos):
        hasta = puntos[i + 1][0] if i + 1 < len(puntos) else ahora
        total += precio * max(0, hasta - max(desde, inicio))
    return total / (ahora - inicio)


def evaluar(producto, previo, cfg, ahora):
    """Devuelve la media de 99 días si el producto acaba de caer por debajo del umbral, o None."""
    if not previo or ahora - previo["p0"] < cfg.horas_min_historial * 3600:
        return None
    if producto.precio >= previo["u"] * BAJADA_MINIMA:
        return None  # no ha bajado desde la última lectura
    media = media_periodo(previo, ahora)
    if not media or media < cfg.precio_min or producto.precio > media * (1 - cfg.descuento_min / 100):
        return None
    return media


def ya_avisado(previo, precio, ahora):
    return bool(previo and previo.get("at", 0) > ahora - HORAS_SIN_REPETIR * 3600
                and precio >= previo["av"] * 0.95)


def actualizar(previo, precio, ahora):
    """Apunta el precio. El historial guarda solo los cambios: [[momento, precio], ...]."""
    ahora = int(ahora)
    if previo is None:
        return {"h": [[ahora, precio]], "u": precio, "p0": ahora, "t": ahora}
    if precio != previo["u"]:
        previo["h"].append([ahora, precio])
    # Se borra lo anterior a 99 días, dejando el último punto como precio al inicio del periodo.
    limite = ahora - DIAS_MEDIA * 86400
    while len(previo["h"]) > 1 and previo["h"][1][0] <= limite:
        previo["h"].pop(0)
    previo.update(u=precio, t=ahora)
    return previo


# --- Avisos ------------------------------------------------------------------

def formatear_precio(euros):
    return f"{euros:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")


def descuento(precio, referencia):
    return (referencia - precio) * 100 / referencia


def mensaje(producto, media, previo, ahora):
    dias = min(DIAS_MEDIA, (ahora - previo["p0"]) / 86400)
    periodo = f"{DIAS_MEDIA} días" if dias >= DIAS_MEDIA else f"{dias:.0f} días de historial" if dias >= 1.5 else "1 día de historial"
    return "\n".join([
        f"🚨 <b>-{descuento(producto.precio, media):.0f}%</b> · {html.escape(producto.titulo[:200])}",
        "",
        f"🏪 {html.escape(producto.tienda)}",
        f"💶 Ahora: <b>{formatear_precio(producto.precio)}</b> (antes {formatear_precio(previo['u'])})",
        f"📊 Precio medio: {formatear_precio(media)} ({periodo})",
        f"💰 Ahorro: {formatear_precio(media - producto.precio)}",
        f"🔗 {html.escape(producto.url)}",
    ])


def resumen_extra(avisos):
    lineas = [f"➕ <b>{len(avisos)} avisos más</b>"]
    for producto, media in avisos:
        lineas.append(f"• -{descuento(producto.precio, media):.0f}% {html.escape(producto.titulo[:60])} "
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

    excluidos = cfg.patron_excluidos()
    productos = estado["productos"]
    candidatos = []
    for lectura in lecturas:
        vistos, nuevos, ignorados = set(), 0, 0
        for producto in lectura.productos:
            if producto.clave in vistos or not producto.precio:
                continue
            vistos.add(producto.clave)
            if excluidos.search(sin_tildes(producto.titulo)):
                ignorados += 1
                productos.pop(producto.clave, None)
                continue
            previo = productos.get(producto.clave)
            nuevos += previo is None
            media = evaluar(producto, previo, cfg, ahora)
            if media and not ya_avisado(previo, producto.precio, ahora):
                candidatos.append((producto, media, dict(previo, h=list(previo["h"]))))
            productos[producto.clave] = actualizar(previo, producto.precio, ahora)
        print(f"{lectura.tienda}: {len(lectura.paginas)} páginas, {len(vistos)} productos "
              f"({nuevos} nuevos, {ignorados} ignorados por tipo)")
        for error in lectura.errores:
            print(f"  ⚠️ {error}", file=sys.stderr)

    candidatos.sort(key=lambda c: descuento(c[0].precio, c[1]), reverse=True)
    enviados = 0
    try:
        for producto, media, previo in candidatos[:cfg.max_avisos]:
            texto = mensaje(producto, media, previo, ahora)
            if simular:
                print("\n" + texto)
            else:
                try:
                    enviar_telegram(cfg, texto, producto.imagen)
                except RuntimeError as e:
                    print(f"No se pudo avisar de {producto.clave}: {e}", file=sys.stderr)
                    continue
                time.sleep(0.5)
            productos[producto.clave].update(av=producto.precio, at=int(ahora))
            enviados += 1
        sobrantes = [(p, m) for p, m, _ in candidatos[cfg.max_avisos:]]
        if sobrantes:
            texto = resumen_extra(sobrantes)
            if simular:
                print("\n" + texto)
            else:
                try:
                    enviar_telegram(cfg, texto)
                except RuntimeError as e:
                    print(f"No se pudo mandar el resumen: {e}", file=sys.stderr)
            for producto, _ in sobrantes:
                productos[producto.clave].update(av=producto.precio, at=int(ahora))
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
