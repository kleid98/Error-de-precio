"""xtralife: videojuegos, consolas y merchandising. Lee las fichas <poster-thumbnail> del HTML."""

import re

from .base import Producto, limpiar, numero

NOMBRE = "xtralife"
BASE = "https://www.xtralife.com"
FIJAS = [f"{BASE}/ofertas-rebajas"]
ROTAR = [f"{BASE}{p}" for p in (
    "/novedades", "/ofertas-nintendo", "/ofertas-playstation",
    "/playstation-5/consolas", "/nintendo-switch-2/consolas",
)]
POR_EJECUCION = 2


def leer(pagina):
    productos = {}
    for bloque in pagina.split("<poster-thumbnail")[1:]:
        bloque = bloque.split("</poster-thumbnail>")[0]
        url = re.search(r'href="(/producto/[^"]+/(\d+))"', bloque)
        titulo = re.search(r"<h3[^>]*>(.*?)</h3>", bloque, re.S)
        precios = re.findall(r'class="fontBold">([\d.,]+)</span>', bloque)
        if not url or not titulo or not precios:
            continue
        tachado = re.search(r'priceCrossed[^>]*>\s*([\d.,]+)', bloque)
        imagen = re.search(r'src="(https://static\.xtralife\.com/conversions/[^"]+)"', bloque)
        productos[url.group(2)] = Producto(
            NOMBRE, url.group(2), limpiar(titulo.group(1)), numero(precios[-1]), BASE + url.group(1),
            precio_ref=numero(tachado.group(1)) if tachado else None,
            imagen=imagen.group(1) if imagen else None,
        )
    return [p for p in productos.values() if p.precio]
