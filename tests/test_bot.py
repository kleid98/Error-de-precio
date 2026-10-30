import json
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

import bot
from tiendas.base import Producto, numero

AHORA = 1_800_000_000


def producto(precio, ref=None, id_="1", tienda="Prueba"):
    return Producto(tienda, id_, "Consola <X>", precio, f"https://tienda.test/{id_}", precio_ref=ref)


def historial(media, ultimo=None, n=10):
    return {"m": media, "n": n, "u": ultimo or media, "t": AHORA - 300}


class Deteccion(unittest.TestCase):
    def setUp(self):
        self.cfg = bot.Config(descuento_min=50, descuento_min_tachado=70, precio_min=30)

    def test_bajada_respecto_a_la_media(self):
        self.assertEqual(bot.evaluar(producto(50), historial(100), True, self.cfg), ("media", 100))
        self.assertIsNone(bot.evaluar(producto(51), historial(100), True, self.cfg))

    def test_media_exige_que_el_precio_acabe_de_bajar(self):
        self.assertIsNone(bot.evaluar(producto(50), historial(100, ultimo=50), True, self.cfg))

    def test_media_respeta_el_precio_minimo(self):
        self.assertIsNone(bot.evaluar(producto(5), historial(20), True, self.cfg))

    def test_producto_nuevo_contra_precio_tachado(self):
        self.assertEqual(bot.evaluar(producto(30, ref=100), None, True, self.cfg), ("tachado", 100))
        self.assertIsNone(bot.evaluar(producto(31, ref=100), None, True, self.cfg))
        self.assertIsNone(bot.evaluar(producto(30), None, True, self.cfg))

    def test_primera_lectura_de_una_pagina_no_avisa(self):
        self.assertIsNone(bot.evaluar(producto(30, ref=100), None, False, self.cfg))

    def test_poco_historial_usa_tachado_solo_si_baja(self):
        poco = historial(30, n=1)
        self.assertIsNone(bot.evaluar(producto(30, ref=100), poco, True, self.cfg))
        self.assertEqual(bot.evaluar(producto(20, ref=100), poco, True, self.cfg), ("tachado", 100))

    def test_no_repite_avisos(self):
        previo = dict(historial(100), av=50, at=AHORA - 3600)
        self.assertTrue(bot.ya_avisado(previo, 49, AHORA))
        self.assertFalse(bot.ya_avisado(previo, 45, AHORA))
        self.assertFalse(bot.ya_avisado(dict(previo, at=AHORA - 4 * 86400), 49, AHORA))

    def test_media_movil(self):
        h = bot.actualizar(None, 100, AHORA)
        self.assertEqual(h, {"m": 100, "n": 1, "u": 100, "t": AHORA})
        bot.actualizar(h, 50, AHORA)
        self.assertEqual((h["m"], h["n"], h["u"]), (75, 2, 50))


class Utilidades(unittest.TestCase):
    def test_numero(self):
        for texto, valor in [("1.299,95 €", 1299.95), ("54,95", 54.95), ("881.95", 881.95),
                             ("1.299", 1299), ("2,30€", 2.3), (139, 139), ("", None), (None, None)]:
            self.assertEqual(numero(texto), valor, texto)

    def test_mensaje(self):
        texto = bot.mensaje(producto(1299.99, ref=5000), "tachado", 5000)
        self.assertIn("-74%", texto)
        self.assertIn("1.299,99 €", texto)
        self.assertIn("Consola &lt;X&gt;", texto)
        self.assertIn("precio tachado de la tienda", texto)


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
        modulo = tienda_falsa({})
        estado = {}
        with mock.patch.object(bot, "pedir", side_effect=lambda url: url):
            leidas = [bot.leer_tienda(modulo, estado, pausa=0).paginas for _ in range(3)]
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

    def test_primera_vuelta_en_silencio_y_luego_avisa(self):
        paginas = {"fija": [producto(40, ref=100, id_="a")]}
        modulo = tienda_falsa(paginas)
        with mock.patch.object(bot.tiendas, "TODAS", [modulo]), \
             mock.patch.object(bot, "pedir", side_effect=lambda url: url), \
             mock.patch.object(bot, "enviar_telegram") as enviar, \
             mock.patch.object(bot, "PAUSA_ENTRE_PAGINAS", 0), \
             mock.patch.object(bot.time, "sleep"):
            bot.ejecutar(self.cfg)  # indexa sin avisar
            paginas["fija"] = [producto(40, ref=100, id_="a"), producto(20, ref=100, id_="b")]
            bot.ejecutar(self.cfg)  # "b" es nuevo y está a -80 % del tachado
            bot.ejecutar(self.cfg)  # no se repite
            for _ in range(3):
                bot.ejecutar(self.cfg)  # "a" acumula historial a 40 €
            paginas["fija"][0] = producto(15, ref=100, id_="a")
            bot.ejecutar(self.cfg)  # "a" cae un 62 % respecto a su media
        avisos = [c.args[1] for c in enviar.call_args_list]
        self.assertEqual(len(avisos), 2)
        self.assertIn("-80%", avisos[0])
        self.assertIn("precio tachado", avisos[0])
        self.assertIn("media vista por el bot", avisos[1])
        estado = json.loads(self.cfg.estado.read_text())
        self.assertEqual(estado["productos"]["Prueba:a"]["av"], 15)


if __name__ == "__main__":
    unittest.main()
