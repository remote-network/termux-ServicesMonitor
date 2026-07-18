import unittest

from _fakes import FakeResponse, FakeSession
import requests
import services_monitor as sm


def servicio(**kw):
    base = dict(nombre="s", url="https://x.test")
    base.update(kw)
    return sm.ServicioConfig(**base)


NOSLEEP = lambda _s: None  # noqa: E731


class TestComprobarServicio(unittest.TestCase):
    def test_activo(self):
        sess = FakeSession(request_results=[FakeResponse(200)])
        r = sm.comprobar_servicio(servicio(), sess, sleep=NOSLEEP)
        self.assertTrue(r.ok)
        self.assertEqual(r.codigo, 200)

    def test_codigo_no_valido(self):
        sess = FakeSession(request_results=[FakeResponse(500)])
        r = sm.comprobar_servicio(servicio(codigos_validos=(200,)), sess, sleep=NOSLEEP)
        self.assertFalse(r.ok)
        self.assertEqual(r.codigo, 500)

    def test_contenido_esperado_ausente(self):
        sess = FakeSession(request_results=[FakeResponse(200, text="hola mundo")])
        r = sm.comprobar_servicio(
            servicio(contenido_esperado="chau"), sess, sleep=NOSLEEP)
        self.assertFalse(r.ok)
        self.assertIn("contenido", r.detalle)

    def test_contenido_esperado_presente(self):
        sess = FakeSession(request_results=[FakeResponse(200, text='{"status":"ok"}')])
        r = sm.comprobar_servicio(
            servicio(contenido_esperado='"status":"ok"'), sess, sleep=NOSLEEP)
        self.assertTrue(r.ok)

    def test_reintenta_y_recupera(self):
        err = requests.exceptions.ConnectionError("boom")
        sess = FakeSession(request_results=[err, err, FakeResponse(200)])
        r = sm.comprobar_servicio(servicio(reintentos=2), sess, sleep=NOSLEEP)
        self.assertTrue(r.ok)
        self.assertEqual(len(sess.request_calls), 3)

    def test_agota_reintentos(self):
        err = requests.exceptions.ConnectionError("boom")
        sess = FakeSession(request_results=[err, err, err])
        r = sm.comprobar_servicio(servicio(reintentos=2), sess, sleep=NOSLEEP)
        self.assertFalse(r.ok)
        self.assertIn("red", r.detalle.lower())
        self.assertEqual(len(sess.request_calls), 3)

    def test_timeout_es_error_de_red(self):
        err = requests.exceptions.Timeout("t")
        sess = FakeSession(request_results=[err])
        r = sm.comprobar_servicio(servicio(reintentos=0), sess, sleep=NOSLEEP)
        self.assertFalse(r.ok)
        self.assertIn("timeout", r.detalle.lower())


if __name__ == "__main__":
    unittest.main()
