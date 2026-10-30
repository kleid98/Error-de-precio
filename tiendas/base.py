"""Piezas comunes de los lectores de tiendas."""

import html
import json
import re
from dataclasses import dataclass


@dataclass
class Producto:
    tienda: str
    id: str
    titulo: str
    precio: float
    url: str
    precio_ref: float | None = None  # precio tachado o "antes" que muestra la propia tienda
    imagen: str | None = None

    @property
    def clave(self):
        return f"{self.tienda}:{self.id}"


def numero(texto):
    """Convierte "1.299,95 €", "54,95" o "881.95" en float. None si no hay número."""
    if texto is None:
        return None
    if isinstance(texto, (int, float)):
        return float(texto)
    t = re.sub(r"[^\d.,]", "", str(texto))
    if not t:
        return None
    if "," in t and "." in t:
        decimal = "," if t.rfind(",") > t.rfind(".") else "."
        miles = "." if decimal == "," else ","
        t = t.replace(miles, "").replace(decimal, ".")
    elif "," in t:
        t = t.replace(",", ".")
    elif re.fullmatch(r"\d{1,3}(\.\d{3})+", t):
        t = t.replace(".", "")  # "1.299" en formato español
    try:
        return float(t)
    except ValueError:
        return None


def limpiar(texto):
    """Quita etiquetas HTML, entidades y espacios sobrantes."""
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", texto or ""))).strip()


def objetos_json(texto, marcador):
    """Decodifica cada objeto JSON que empieza en una aparición de `marcador` (p. ej. '{"id":')."""
    decodificador = json.JSONDecoder()
    i = 0
    while (i := texto.find(marcador, i)) != -1:
        try:
            objeto, fin = decodificador.raw_decode(texto, i)
        except ValueError:
            i += 1
            continue
        yield objeto
        i = fin


def productos_jsonld(pagina):
    """Productos con precio de los bloques JSON-LD (schema.org) de una página."""
    encontrados = []

    def recorrer(nodo):
        if isinstance(nodo, list):
            for x in nodo:
                recorrer(x)
        elif isinstance(nodo, dict):
            if nodo.get("@type") == "Product" and isinstance(nodo.get("offers"), dict):
                encontrados.append(nodo)
            for valor in nodo.values():
                recorrer(valor)

    for m in re.finditer(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', pagina, re.S):
        try:
            recorrer(json.loads(m.group(1)))
        except ValueError:
            continue
    return encontrados
