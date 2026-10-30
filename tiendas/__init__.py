"""Lectores de tiendas. Cada módulo define:

    NOMBRE         nombre de la tienda en los avisos
    FIJAS          páginas que se leen en cada búsqueda (ofertas, novedades…)
    ROTAR          páginas que se reparten entre búsquedas, POR_EJECUCION cada vez
    leer(html)     -> lista de base.Producto
    descubrir(html) (opcional) -> más páginas para ROTAR, sacadas de las FIJAS
"""

from . import conforama, druni, game, ikea, ldlc, lidl, miravia, tiendanimal, xtralife

TODAS = [ldlc, game, xtralife, druni, lidl, ikea, conforama, tiendanimal, miravia]
