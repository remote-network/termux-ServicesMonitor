import signal
import tempfile
import unittest
from pathlib import Path

from _fakes import FakeResponse, FakeSession
import services_monitor as sm


def ajustes(ruta, servicios):
    return sm.Ajustes(intervalo=60, servicios=servicios,
                      telegram_token="tok", telegram_chat_id="chat", ruta_estado=ruta)


class TestMonitorRun(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.ruta = Path(self.dir.name) / "estado.json"
        self.srv = sm.ServicioConfig(nombre="web", url="https://x.test")

    def tearDown(self):
        self.dir.cleanup()

    def test_una_vez_envia_resumen_y_guarda_estado(self):
        sess = FakeSession(request_results=[FakeResponse(200)],
                           post_results=[FakeResponse(200, json_data={"ok": True})])
        notifier = sm.Notifier("tok", "chat", sess)
        mon = sm.Monitor(ajustes(self.ruta, [self.srv]), sess, notifier)
        mon.run(una_vez=True)

        self.assertEqual(len(sess.post_calls), 1)                 # resumen de inicio
        self.assertIn("Monitor HTTP iniciado", sess.post_calls[0][1]["json"]["text"])
        estado = sm.cargar_estado(self.ruta)
        self.assertEqual(estado["web"]["confirmado"], "up")       # baseline persistido

    def test_senal_marca_stop(self):
        sess = FakeSession()
        mon = sm.Monitor(ajustes(self.ruta, [self.srv]), sess,
                         sm.Notifier("tok", "chat", sess))
        self.assertFalse(mon.stop.is_set())
        mon.manejar_senal(signal.SIGTERM, None)
        self.assertTrue(mon.stop.is_set())


if __name__ == "__main__":
    unittest.main()
