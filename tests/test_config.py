import json
import os
import unittest
from unittest import mock

from _fakes import *  # noqa: F401,F403  (ajusta sys.path)
import services_monitor as sm

DEF = {"timeout": 10.0, "umbral_fallos": 2, "umbral_exitos": 1,
       "reintentos": 2, "backoff_base": 1.0}


class TestConstruirServicio(unittest.TestCase):
    def test_minimo_valido_aplica_defaults(self):
        s = sm.construir_servicio({"nombre": "web", "url": "https://x.test"}, 0, DEF)
        self.assertEqual(s.nombre, "web")
        self.assertEqual(s.metodo, "GET")
        self.assertEqual(s.codigos_validos, (200,))
        self.assertEqual(s.umbral_fallos, 2)

    def test_completo(self):
        s = sm.construir_servicio({
            "nombre": "api", "url": "https://x.test", "metodo": "head",
            "timeout": 5, "codigos_validos": [200, 204],
            "headers": {"A": "b"}, "contenido_esperado": "ok",
            "umbral_fallos": 3, "reintentos": 0,
        }, 0, DEF)
        self.assertEqual(s.metodo, "HEAD")
        self.assertEqual(s.codigos_validos, (200, 204))
        self.assertEqual(s.headers, {"A": "b"})
        self.assertEqual(s.contenido_esperado, "ok")

    def test_falta_url(self):
        with self.assertRaises(sm.ConfigError):
            sm.construir_servicio({"nombre": "x"}, 0, DEF)

    def test_url_sin_esquema(self):
        with self.assertRaises(sm.ConfigError):
            sm.construir_servicio({"nombre": "x", "url": "ftp://x"}, 0, DEF)

    def test_metodo_invalido(self):
        with self.assertRaises(sm.ConfigError):
            sm.construir_servicio({"nombre": "x", "url": "https://x", "metodo": "FLY"}, 0, DEF)

    def test_codigos_no_lista(self):
        with self.assertRaises(sm.ConfigError):
            sm.construir_servicio(
                {"nombre": "x", "url": "https://x", "codigos_validos": "200"}, 0, DEF)

    def test_timeout_invalido(self):
        with self.assertRaises(sm.ConfigError):
            sm.construir_servicio({"nombre": "x", "url": "https://x", "timeout": 0}, 0, DEF)

    def test_headers_no_texto(self):
        with self.assertRaises(sm.ConfigError):
            sm.construir_servicio(
                {"nombre": "x", "url": "https://x", "headers": {"A": 1}}, 0, DEF)


class TestConstruirServicios(unittest.TestCase):
    def test_nombres_duplicados(self):
        datos = [{"nombre": "a", "url": "https://x"}, {"nombre": "a", "url": "https://y"}]
        with self.assertRaises(sm.ConfigError):
            sm.construir_servicios(datos, DEF)

    def test_lista_vacia(self):
        with self.assertRaises(sm.ConfigError):
            sm.construir_servicios([], DEF)


class TestCargarAjustes(unittest.TestCase):
    def _env(self, **extra):
        base = {"TELEGRAM_BOT_TOKEN": "tok", "TELEGRAM_CHAT_ID": "123",
                "SERVICES_JSON": json.dumps([{"nombre": "a", "url": "https://x.test"}])}
        base.update(extra)
        return base

    def test_valido(self):
        with mock.patch.dict(os.environ, self._env(), clear=True):
            aj = sm.cargar_ajustes()
        self.assertEqual(len(aj.servicios), 1)
        self.assertEqual(aj.telegram_token, "tok")
        self.assertEqual(aj.intervalo, 60)

    def test_falta_token(self):
        env = self._env()
        del env["TELEGRAM_BOT_TOKEN"]
        with mock.patch.dict(os.environ, env, clear=True):
            with self.assertRaises(sm.ConfigError):
                sm.cargar_ajustes()

    def test_intervalo_invalido(self):
        with mock.patch.dict(os.environ, self._env(CHECK_INTERVAL="0"), clear=True):
            with self.assertRaises(sm.ConfigError):
                sm.cargar_ajustes()


if __name__ == "__main__":
    unittest.main()
