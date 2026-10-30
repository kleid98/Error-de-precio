"""Miravia: ofertas flash (datos de la primera pantalla que la web incrusta en el HTML)."""

import json

from .base import Producto, numero

NOMBRE = "Miravia"
FIJAS = ["https://www.miravia.es/flashsale/home"]
ROTAR = []
POR_EJECUCION = 0
MARCADOR = "window.__FIRST_SCREEN_DATA="


def leer(pagina):
    inicio = pagina.find(MARCADOR)
    if inicio == -1:
        return []
    try:
        datos, _ = json.JSONDecoder().raw_decode(pagina, inicio + len(MARCADOR))
    except ValueError:
        return []
    productos = {}

    def recorrer(nodo):
        if isinstance(nodo, list):
            for x in nodo:
                recorrer(x)
        elif isinstance(nodo, dict):
            if "itemId" in nodo and "itemDiscountPrice" in nodo:
                precio = numero(nodo["itemDiscountPrice"])
                if precio:
                    productos[nodo["itemId"]] = Producto(
                        NOMBRE, nodo["itemId"], nodo.get("itemTitle", ""), precio,
                        "https:" + nodo.get("itemUrl", "") if nodo.get("itemUrl", "").startswith("//") else nodo.get("itemUrl", ""),
                        precio_ref=numero(nodo.get("itemPrice")), imagen=nodo.get("itemImg"),
                    )
            for valor in nodo.values():
                recorrer(valor)

    recorrer(datos)
    return list(productos.values())
