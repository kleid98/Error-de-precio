"""GAME: consolas, videojuegos y PC gaming. Lee los datos que Next.js incrusta en la página (24 por página)."""

import json
import re

from .base import Producto, numero, objetos_json

NOMBRE = "GAME"
BASE = "https://www.game.es"
FIJAS = [f"{BASE}/ofertas", f"{BASE}/ofertas?pagina=2", f"{BASE}/novedades"]
ROTAR = (
    [f"{BASE}/ofertas?pagina={n}" for n in range(3, 81)]
    + [f"{BASE}/consolas-y-videojuegos/consolas?pagina={n}" for n in range(1, 13)]
    + [f"{BASE}/consolas-y-videojuegos/videojuegos?pagina={n}" for n in range(1, 6)]
    + [f"{BASE}/consolas-y-videojuegos/consolas-portatiles-pc",
       f"{BASE}/pc-gaming/sobremesas-gaming",
       f"{BASE}/juegos-de-mesa-coleccionables-y-tcg/juegos-de-mesa"]
)
POR_EJECUCION = 5


def leer(pagina):
    trozos = re.findall(r'self\.__next_f\.push\(\[1,(".*?")\]\)</script>', pagina, re.S)
    datos = "".join(json.loads(t) for t in trozos)
    productos = {}
    for item in objetos_json(datos, '{"id":"'):
        precios = item.get("pricing") if isinstance(item, dict) else None
        if not isinstance(precios, dict) or not item.get("url"):
            continue
        precio = numero(precios.get("current"))
        if not precio:
            continue
        productos[item["id"]] = Producto(
            NOMBRE, item["id"], item.get("title", ""), precio, BASE + item["url"],
            precio_ref=numero(precios.get("recommended")), imagen=item.get("src"),
        )
    return list(productos.values())
