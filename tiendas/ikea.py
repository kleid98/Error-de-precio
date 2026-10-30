"""IKEA: secciones de bajadas de precio y última oportunidad (24 productos por página)."""

import re

from .base import Producto, limpiar, numero

NOMBRE = "IKEA"
BASE = "https://www.ikea.com/es/es/cat/"
FIJAS = [BASE + "lower-price/", BASE + "last-chance/", BASE + "lowest-price/"]
ROTAR = []
POR_EJECUCION = 0


def leer(pagina):
    productos = {}
    for tarjeta in re.split(r'(?=<div class="plp-mastercard )', pagina)[1:]:
        cabecera = tarjeta[:tarjeta.find(">")]
        ident = re.search(r'data-product-number="(\w+)"', cabecera)
        precio = re.search(r'data-price="([\d.]+)"', cabecera)
        nombre = re.search(r'data-product-name="([^"]*)"', cabecera)
        url = re.search(r'href="(https://www\.ikea\.com/es/es/p/[^"]+)"', tarjeta)
        if not (ident and precio and url):
            continue
        tipo = re.search(r'comparar productos, ([^"]+)"', tarjeta)
        anterior = re.search(r"Precio anterior\s*([\d.,]+)", tarjeta)
        imagen = re.search(r'<img[^>]*src="([^"]+)"', tarjeta)
        titulo = " ".join(filter(None, [nombre and limpiar(nombre.group(1)), tipo and limpiar(tipo.group(1))]))
        productos[ident.group(1)] = Producto(
            NOMBRE, ident.group(1), titulo, float(precio.group(1)), url.group(1),
            precio_ref=numero(anterior.group(1)) if anterior else None,
            imagen=imagen.group(1).split("?")[0] if imagen else None,
        )
    return list(productos.values())
