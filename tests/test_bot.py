import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import bot


def oferta(id_=1, precio=10.0, habitual=50.0, titulo="Producto <de> prueba", tienda="Amazon", **extra):
    return {
        "threadId": id_, "type": "Deal", "title": titulo, "titleSlug": "producto-de-prueba",
        "price": precio, "nextBestPrice": habitual, "isExpired": False, "isLocal": False,
        "merchant": {"merchantName": tienda},
        "mainImage": {"path": "threads/raw/AbC", "name": f"{id_}_1"},
        **extra,
    }


class Pruebas(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg = bot.Config("t", "c", estado=Path(self.tmp.name) / "vistos.json")

    def tearDown(self):
        self.tmp.cleanup()

    def test_extrae_ofertas_del_html(self):
        pagina = '<script>x = {"a":[' + json.dumps(oferta(7)) + ',' + json.dumps(oferta(7)) + \
                 ']}; {"threadId": roto</script>'
        self.assertEqual([o["threadId"] for o in bot.extraer_ofertas(pagina)], [7])

    def test_descuento_minimo(self):
        self.assertTrue(bot.es_chollo(oferta(precio=25, habitual=50), self.cfg))
        self.assertFalse(bot.es_chollo(oferta(precio=25.01, habitual=50), self.cfg))
        self.assertFalse(bot.es_chollo(oferta(habitual=0), self.cfg))

    def test_error_de_precio_en_titulo(self):
        self.assertTrue(bot.es_chollo(oferta(habitual=0, titulo="ERROR DE PRECIO: tele 4K"), self.cfg))

    def test_descarta_caducadas_locales_y_otras_tiendas(self):
        self.assertFalse(bot.es_chollo(oferta(isExpired=True), self.cfg))
        self.assertFalse(bot.es_chollo(oferta(isLocal=True), self.cfg))
        self.cfg.tiendas = ["amazon"]
        self.assertFalse(bot.es_chollo(oferta(tienda="Fnac"), self.cfg))
        self.assertTrue(bot.es_chollo(oferta(tienda="Amazon"), self.cfg))

    def test_mensaje(self):
        texto = bot.mensaje(oferta(precio=1299.99, habitual=5000))
        self.assertIn("-74%", texto)
        self.assertIn("1.299,99 €", texto)
        self.assertIn("&lt;de&gt;", texto)
        self.assertIn("https://www.chollometro.com/ofertas/producto-de-prueba-1", texto)
        self.assertEqual(bot.imagen(oferta()),
                         "https://static.chollometro.com/threads/raw/AbC/1_1/re/300x300/qt/60/1_1.jpg")

    def test_ejecutar_avisa_una_vez_y_guarda_estado(self):
        ofertas = [oferta(1, 20), oferta(2, 5), oferta(3, 45)]
        with mock.patch.object(bot, "buscar_ofertas", return_value=ofertas), \
             mock.patch.object(bot, "enviar_telegram") as enviar:
            bot.ejecutar(self.cfg)
            bot.ejecutar(self.cfg)
        # La 2 (-90 %) primero, la 3 (-10 %) no cuenta, y la segunda ejecución no repite.
        self.assertEqual(enviar.call_count, 2)
        self.assertIn("-90%", enviar.call_args_list[0].args[1])
        self.assertEqual(set(json.loads(self.cfg.estado.read_text())), {"1", "2"})


if __name__ == "__main__":
    unittest.main()
