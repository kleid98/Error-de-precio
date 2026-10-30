"""Tiendanimal: ofertas para mascotas (Salesforce Commerce Cloud, 24 por página)."""

import html
import re

from .base import Producto, limpiar, numero

NOMBRE = "Tiendanimal"
BASE = "https://www.tiendanimal.es/ofertas/"
FIJAS = [BASE]
ROTAR = [f"{BASE}?start={n * 24}&sz=24" for n in range(1, 30)]
POR_EJECUCION = 3


def leer(pagina):
    productos = {}
    for bloque in pagina.split('data-product-name="')[1:]:
        bloque = bloque[:12000]
        nombre = bloque[:bloque.find('"')]
        ident = re.search(r'data-pid="([^"]+)"', bloque)
        url = re.search(r'href="(https://www\.tiendanimal\.es/[^"]+\.html)"', bloque)
        minimo = re.search(r'data-min-price="([\d.]+)"', bloque)
        if not (ident and url and minimo):
            continue
        marca = re.search(r'data-brand="([^"]*)"', bloque)
        con_dto = re.search(r'price-discount">([^<]+)', bloque)
        lista = re.search(r'price-list">([^<]+)', bloque)
        imagen = re.search(r'<img[^>]*src="([^"]+)"', bloque)
        titulo = limpiar(nombre)
        if marca and marca.group(1) not in ("", "false") and not titulo.lower().startswith(marca.group(1).lower()):
            titulo = f"{limpiar(marca.group(1))} {titulo}"
        productos[ident.group(1)] = Producto(
            NOMBRE, ident.group(1), titulo,
            numero(html.unescape(con_dto.group(1))) if con_dto else float(minimo.group(1)), url.group(1),
            precio_ref=numero(html.unescape(lista.group(1))) if lista else None,
            imagen=html.unescape(imagen.group(1)) if imagen else None,
        )
    return [p for p in productos.values() if p.precio]
