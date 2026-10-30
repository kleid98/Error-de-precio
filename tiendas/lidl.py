"""Lidl: lee el JSON de cada producto (data-grid-data). Las secciones cambian cada semana,
así que se descubren en la portada."""

import html
import json
import re

from .base import Producto, limpiar

NOMBRE = "Lidl"
BASE = "https://www.lidl.es"
FIJAS = [f"{BASE}/", f"{BASE}/c/ofertas-semanales/a10089449", f"{BASE}/c/super-finde/a10089450"]
ROTAR = [f"{BASE}/c/bricolaje/a10103549", f"{BASE}/c/bajadas-permanentes/a10089468"]
POR_EJECUCION = 4


def descubrir(pagina):
    """Secciones de la portada para añadir a la rotación."""
    return [BASE + ruta for ruta in re.findall(r'href="(?:https://www\.lidl\.es)?(/c/[a-z0-9-]+/a\d+)"', pagina)]


def leer(pagina):
    productos = {}
    for m in re.finditer(r'data-grid-data="([^"]+)"', pagina):
        try:
            datos = json.loads(html.unescape(m.group(1)))
        except ValueError:
            continue
        for d in datos if isinstance(datos, list) else [datos]:
            precios = d.get("price") if isinstance(d, dict) else None
            if not isinstance(precios, dict) or not precios.get("price") or not d.get("productId"):
                continue
            ruta = d.get("canonicalUrl") or d.get("canonicalPath") or ""
            productos[str(d["productId"])] = Producto(
                NOMBRE, str(d["productId"]), limpiar(d.get("fullTitle") or d.get("title")), float(precios["price"]),
                ruta if ruta.startswith("http") else BASE + ruta,
                precio_ref=precios.get("oldPrice"), imagen=d.get("image"),
            )
    return list(productos.values())
