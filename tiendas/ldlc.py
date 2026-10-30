"""LDLC: informática, consolas y LEGO. Precios del JSON-LD de cada categoría (48 por página)."""

import re

from .base import Producto, numero, productos_jsonld

NOMBRE = "LDLC"
BASE = "https://www.ldlc.com/es-es/"
CATEGORIAS = [
    "informatica/piezas-de-informatica/tarjeta-grafica/c4684/",
    "informatica/piezas-de-informatica/procesador/c4300/",
    "informatica/piezas-de-informatica/disco-ssd/c4698/",
    "informatica/piezas-de-informatica/memoria-pc/c4703/",
    "informatica/piezas-de-informatica/placa-base/c4293/",
    "informatica/piezas-de-informatica/fuente-de-alimentacion/c4289/",
    "informatica/piezas-de-informatica/caja-de-pc/c4678/",
    "informatica/perifericos-pc/pantalla-pc/c4623/",
    "informatica/ordenador-portatil/portatil/c4265/",
    "informatica/ordenador-portatil/macbook/c4266/",
    "informatica/ordenador-de-mesa/ordenador-mac/c4796/",
    "informatica/ordenador-de-mesa/pc-de-sobremesa/c4250/",
    "informatica/tablet/tableta-tactil/c4271/",
    "juegos-y-ocio/consola/consola-ps5/c7865/",
    "juegos-y-ocio/consola/consola-nintendo-switch-2/c8510/",
    "juegos-y-ocio/consola/consola-nintendo-switch/c7600/",
    "juegos-y-ocio/consola/consola-xbox-series/c7866/",
    "juegos-y-ocio/consola/otras-consolas/c7763/",
    "juegos-y-ocio/accesorios-para-consolas-y-pc/accesorios-ps5/c7869/",
    "juegos-y-ocio/accesorios-para-consolas-y-pc/joypad/c4435/",
    "juegos-y-ocio/gaming-vr/gafas-realidad-virtual/c7940/",
    "juegos-y-ocio/lego/c8162/",
    "imagen-y-sonido/sonido-digital/auriculares/c4380/",
    "imagen-y-sonido/home-cinema-y-hifi/casco-de-audio/c4336/",
    "imagen-y-sonido/home-cinema-y-hifi/barra-de-sonido/c4335/",
    "imagen-y-sonido/television/tv/c4402/",
    "imagen-y-sonido/camara-de-fotos/camara-de-fotos-hibrida/c4363/",
    "imagen-y-sonido/sonido-digital/dock-y-altavoces-bluetooth/c4389/",
    "imagen-y-sonido/lector-ebook/c5268/",
]
FIJAS = []
ROTAR = [BASE + c + (f"pagina{n}/" if n > 1 else "") for n in (1, 2, 3) for c in CATEGORIAS]
POR_EJECUCION = 8


def leer(pagina):
    productos = []
    for p in productos_jsonld(pagina):
        url = p.get("url") or ""
        ident = re.search(r"/(PB\d+)\.html", url)
        precio = numero(p["offers"].get("price"))
        if not ident or not precio:
            continue
        productos.append(Producto(NOMBRE, ident.group(1), p.get("name", ""), precio, url, imagen=p.get("image")))
    return productos
