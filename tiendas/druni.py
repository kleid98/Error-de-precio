"""Druni: perfumería y cosmética (Magento, 24 productos por página con "precio habitual")."""

import html
import re

from .base import Producto, limpiar

NOMBRE = "Druni"
BASE = "https://www.druni.es"
FIJAS = [f"{BASE}/ofertas-flash", f"{BASE}/novedades/", f"{BASE}/black-friday"]
CATEGORIAS = [
    "/perfumes/mujer", "/perfumes/hombre", "/perfumes/premium/mujer", "/perfumes/premium/hombre",
    "/perfumes/unisex", "/perfumes/estuches/mujer", "/perfumes/estuches/hombre", "/perfumes/novedades",
    "/maquillaje/lujo", "/cosmetica/lujo",
]
ROTAR = [f"{BASE}{c}" + (f"?p={n}" if n > 1 else "") for n in (1, 2, 3, 4, 5) for c in CATEGORIAS]
POR_EJECUCION = 5


def leer(pagina):
    productos = {}
    for bloque in pagina.split('class="item product product-item')[1:]:
        bloque = bloque[:15000]
        ident = re.search(r'data-product-id="(\d+)"', bloque)
        precio = re.search(r'data-price-amount="([\d.]+)"\s+data-price-type="finalPrice"', bloque)
        url = re.search(r'href="(https://www\.druni\.es/[^"]+)"[^>]*class="product-item-link', bloque) \
            or re.search(r'class="product-item-link"[^>]*href="([^"]+)"', bloque) \
            or re.search(r'href="(https://www\.druni\.es/[^"?]+)"', bloque)
        if not (ident and precio and url):
            continue
        habitual = re.search(r'data-price-amount="([\d.]+)"\s+data-price-type="oldPrice"', bloque)
        marca = re.search(r'class="product-brand[^"]*"[^>]*>([^<]*)<', bloque)
        nombre = re.search(r'<img[^>]*alt="([^"]*)"', bloque)
        imagen = re.search(r'<img[^>]*src="(https://www\.druni\.es/media/[^"?]+)', bloque)
        titulo = " ".join(filter(None, [marca and limpiar(marca.group(1)).title(),
                                        nombre and html.unescape(nombre.group(1))]))
        productos[ident.group(1)] = Producto(
            NOMBRE, ident.group(1), titulo, float(precio.group(1)), url.group(1),
            precio_ref=float(habitual.group(1)) if habitual else None,
            imagen=imagen.group(1) if imagen else None,
        )
    return list(productos.values())
