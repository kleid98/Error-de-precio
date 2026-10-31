import json
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

import bot
from tiendas.base import Producto, numero

DIA = 86400
AHORA = 1_800_000_000


def producto(precio, ref=None, id_="1", titulo="Consola <X>"):
    return Producto("Prueba", id_, titulo, precio, f"https://tienda.test/{id_}", precio_ref=ref)


def historial(*puntos):
    """puntos: (días atrás, precio) en orden cronológico."""
    h = [[AHORA - dias * DIA, precio] for dias, precio in puntos]
    return {"h": h, "u": h[-1][1], "p0": h[0][0], "t": AHORA - 300}


class Media(unittest.TestCase):
    def test_media_ponderada_por_tiempo(self):
        # 45 días a 100 € y los últimos 45 a 200 €
        self.assertAlmostEqual(bot.media_periodo(historial((90, 100), (45, 200)), AHORA), 150)

    def test_solo_cuentan_los_ultimos_99_dias(self):
        # Hace 200 días valía 1000 €, pero desde hace 150 vale 100 €
        self.assertAlmostEqual(bot.media_periodo(historial((200, 1000), (150, 100)), AHORA), 100)

    def test_actualizar_guarda_solo_cambios_y_poda(self):
        h = bot.actualizar(None, 100, AHORA - 200 * DIA)
        bot.actualizar(h, 100, AHORA - 150 * DIA)
        self.assertEqual(len(h["h"]), 1)
        bot.actualizar(h, 80, AHORA - 120 * DIA)
        bot.actualizar(h, 90, AHORA)
        # El punto de hace 200 días se borra; el de hace 120 queda como precio al inicio del periodo.
        self.assertEqual(h["h"], [[AHORA - 120 * DIA, 80], [AHORA, 90]])
        self.assertEqual((h["u"], h["p0"]), (90, AHORA - 200 * DIA))


class Deteccion(unittest.TestCase):
    def setUp(self):
        self.cfg = bot.Config(descuento_min=50, precio_min=30, horas_min_historial=24)

    def test_avisa_al_caer_un_50_por_ciento_bajo_la_media(self):
        previo = historial((90, 100))
        self.assertAlmostEqual(bot.evaluar(producto(50), previo, self.cfg, AHORA), 100)
        self.assertIsNone(bot.evaluar(producto(51), previo, self.cfg, AHORA))

    def test_ignora_el_precio_tachado(self):
        self.assertIsNone(bot.evaluar(producto(10, ref=1000), None, self.cfg, AHORA))
        self.assertIsNone(bot.evaluar(producto(60, ref=1000), historial((90, 100)), self.cfg, AHORA))

    def test_exige_historial_minimo(self):
        self.assertIsNone(bot.evaluar(producto(40), historial((0.5, 100)), self.cfg, AHORA))
        self.assertIsNotNone(bot.evaluar(producto(40), historial((1.5, 100)), self.cfg, AHORA))

    def test_exige_que_acabe_de_bajar(self):
        self.assertIsNone(bot.evaluar(producto(40), historial((90, 100), (1, 40)), self.cfg, AHORA))

    def test_respeta_el_precio_minimo(self):
        self.assertIsNone(bot.evaluar(producto(5), historial((90, 20)), self.cfg, AHORA))

    def test_no_repite_avisos(self):
        previo = dict(historial((90, 100)), av=50, at=AHORA - 3600)
        self.assertTrue(bot.ya_avisado(previo, 49, AHORA))
        self.assertFalse(bot.ya_avisado(previo, 45, AHORA))
        self.assertFalse(bot.ya_avisado(dict(previo, at=AHORA - 4 * DIA), 49, AHORA))

    def test_excluye_tipos_de_producto(self):
        patron = bot.Config(excluir=["Funko"]).patron_excluidos()
        for titulo in ["Chaqueta de esquí para mujer", "Sofá cama LUCY", "Armario MOKARIS",
                       "Portátil ASUS reacondicionado", "Silla gaming", "Pantalón", "FUNKO Pop Batman"]:
            self.assertTrue(patron.search(bot.sin_tildes(titulo)), titulo)
        for titulo in ["PlayStation 5 Slim", "Juego de mesa Catan", "LEGO Star Wars", "Dior Sauvage",
                       "PARKSIDE Taladro", "Tarjeta gráfica RTX 5070"]:
            self.assertFalse(patron.search(bot.sin_tildes(titulo)), titulo)


class Pausa(unittest.TestCase):
    def test_pausa_nocturna(self):
        cfg = bot.Config(pausa=(1, 9))
        horas = {h: cfg.en_pausa(bot.datetime(2026, 1, 1, h, 30)) for h in range(24)}
        self.assertEqual([h for h, pausa in horas.items() if pausa], list(range(1, 9)))

    def test_pausa_que_cruza_medianoche(self):
        cfg = bot.Config(pausa=(23, 7))
        self.assertTrue(cfg.en_pausa(bot.datetime(2026, 1, 1, 23, 0)))
        self.assertTrue(cfg.en_pausa(bot.datetime(2026, 1, 1, 3, 0)))
        self.assertFalse(cfg.en_pausa(bot.datetime(2026, 1, 1, 7, 0)))

    def test_sin_pausa(self):
        self.assertFalse(bot.Config(pausa=None).en_pausa(bot.datetime(2026, 1, 1, 3, 0)))

    def test_variable_de_entorno(self):
        with mock.patch.dict("os.environ", {"PAUSA_NOCHE": "2-8"}):
            self.assertEqual(bot.Config.desde_entorno().pausa, (2, 8))
        with mock.patch.dict("os.environ", {"PAUSA_NOCHE": "no"}):
            self.assertIsNone(bot.Config.desde_entorno().pausa)


class Utilidades(unittest.TestCase):
    def test_numero(self):
        for texto, valor in [("1.299,95 €", 1299.95), ("54,95", 54.95), ("881.95", 881.95),
                             ("1.299", 1299), ("2,30€", 2.3), (139, 139), ("", None), (None, None)]:
            self.assertEqual(numero(texto), valor, texto)

    def test_mensaje(self):
        texto = bot.mensaje(producto(1299.99), 5000, historial((30, 5000)), AHORA)
        self.assertIn("-74%", texto)
        self.assertIn("1.299,99 €", texto)
        self.assertIn("Consola &lt;X&gt;", texto)
        self.assertIn("30 días de historial", texto)
        self.assertIn("99 días", bot.mensaje(producto(10), 50, historial((120, 50)), AHORA))


def tienda_falsa(paginas):
    """Módulo de tienda que devuelve los productos indicados para cada URL."""
    return types.SimpleNamespace(
        NOMBRE="Prueba", FIJAS=["fija"], ROTAR=["r1", "r2", "r3"], POR_EJECUCION=2,
        leer=lambda url: paginas.get(url, []),
    )


class Busqueda(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg = bot.Config("t", "c", estado=Path(self.tmp.name) / "historial.json")
        self.silencio = mock.patch("builtins.print")
        self.silencio.start()

    def tearDown(self):
        self.silencio.stop()
        self.tmp.cleanup()

    def test_rotacion_de_paginas(self):
        estado = {}
        with mock.patch.object(bot, "pedir", side_effect=lambda url: url):
            leidas = [bot.leer_tienda(tienda_falsa({}), estado, pausa=0).paginas for _ in range(3)]
        self.assertEqual(leidas, [["fija", "r1", "r2"], ["fija", "r3", "r1"], ["fija", "r2", "r3"]])

    def test_errores_de_red_no_paran_la_tienda(self):
        def pedir(url):
            if url == "r1":
                raise RuntimeError("HTTP 503")
            return url
        with mock.patch.object(bot, "pedir", side_effect=pedir):
            lectura = bot.leer_tienda(tienda_falsa({}), {}, pausa=0)
        self.assertEqual(lectura.paginas, ["fija", "r2"])
        self.assertTrue(any("HTTP 503" in e for e in lectura.errores))

    def test_tienda_que_no_responde_se_deja(self):
        pedidas = []
        def pedir(url):
            pedidas.append(url)
            raise RuntimeError("sin respuesta (URLError)")
        with mock.patch.object(bot, "pedir", side_effect=pedir):
            lectura = bot.leer_tienda(tienda_falsa({}), {}, pausa=0)
        self.assertEqual(pedidas, ["fija", "r1"])
        self.assertTrue(any("no responde" in e for e in lectura.errores))

    def test_avisa_solo_con_historial_y_una_vez(self):
        paginas = {"fija": [producto(100, ref=500, id_="a"), producto(100, id_="b", titulo="Sofá cama")]}
        reloj = [AHORA]
        with mock.patch.object(bot.tiendas, "TODAS", [tienda_falsa(paginas)]), \
             mock.patch.object(bot, "pedir", side_effect=lambda url: url), \
             mock.patch.object(bot, "enviar_telegram") as enviar, \
             mock.patch.object(bot.time, "time", side_effect=lambda: reloj[0]), \
             mock.patch.object(bot.time, "sleep"):
            bot.ejecutar(self.cfg)                       # apunta "a" a 100 €; el sofá se ignora
            reloj[0] += 2 * DIA
            paginas["fija"] = [producto(45, id_="a"), producto(10, id_="b", titulo="Sofá cama")]
            bot.ejecutar(self.cfg)                       # "a" cae un 55 %: aviso
            reloj[0] += 600
            bot.ejecutar(self.cfg)                       # sigue igual: no se repite
        self.assertEqual(enviar.call_count, 1)
        self.assertIn("-55%", enviar.call_args.args[1])
        estado = json.loads(self.cfg.estado.read_text())
        self.assertEqual(set(estado["productos"]), {"Prueba:a"})
        self.assertEqual(estado["productos"]["Prueba:a"]["av"], 45)


if __name__ == "__main__":
    unittest.main()
