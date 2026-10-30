"""Conforama: ofertas y liquidación (30 productos por página con precio original tachado)."""

import re

from .base import Producto, limpiar, numero

NOMBRE = "Conforama"
BASE = "https://www.conforama.es/ofertas-y-liquidacion"
FIJAS = [BASE]
ROTAR = [f"{BASE}?page={n}" for n in range(2, 61)]
POR_EJECUCION = 3


def leer(pagina):
    productos = {}
    for bloque in pagina.split("<article data-itemreference")[1:]:
        bloque = bloque.split("</article>")[0]
        ident = re.search(r'^="(\w+)"', bloque)
        nombre = re.search(r'data-gtm-detail-item-name="([^"]*)"', bloque)
        url = re.search(r'href="(https://www\.conforama\.es/[^"]+)"', bloque)
        precio = re.search(r'class="selling-price[^"]*"[^>]*>([^<]+)', bloque)
        if not (ident and nombre and url and precio and numero(precio.group(1))):
            continue
        original = re.search(r'class="original-price[^"]*"[^>]*>([^<]+)', bloque)
        imagen = re.search(r'<img[^>]*src="([^"]+)"', bloque)
        productos[ident.group(1)] = Producto(
            NOMBRE, ident.group(1), limpiar(nombre.group(1)), numero(precio.group(1)), url.group(1),
            precio_ref=numero(original.group(1)) if original else None,
            imagen=limpiar(imagen.group(1)) if imagen else None,
        )
    return list(productos.values())
