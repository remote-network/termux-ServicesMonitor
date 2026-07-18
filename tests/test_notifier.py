import unittest

from _fakes import FakeResponse, FakeSession
import requests
import services_monitor as sm

TOKEN = "123456:AA_super_secreto"
CHAT = "987654"


class TestNotifier(unittest.TestCase):
    def test_envio_ok(self):
        sess = FakeSession(post_results=[FakeResponse(200, json_data={"ok": True})])
        n = sm.Notifier(TOKEN, CHAT, sess)
        self.assertTrue(n.enviar("hola"))
        # El token viaja en la URL de la API (correcto), pero nunca se logea.
        self.assertIn(TOKEN, sess.post_calls[0][0])

    def test_api_rechaza(self):
        sess = FakeSession(post_results=[FakeResponse(200, json_data={"ok": False,
                                                                      "description": "bad"})])
        n = sm.Notifier(TOKEN, CHAT, sess)
        with self.assertLogs("services_monitor", level="ERROR"):
            self.assertFalse(n.enviar("hola"))

    def test_error_red_no_filtra_secretos(self):
        # La excepción incluye el token (como haría requests con la URL real).
        err = requests.exceptions.ConnectionError(
            f"HTTPSConnectionPool: url=https://api.telegram.org/bot{TOKEN}/sendMessage")
        sess = FakeSession(post_results=[err])
        n = sm.Notifier(TOKEN, CHAT, sess)
        with self.assertLogs("services_monitor", level="ERROR") as cm:
            self.assertFalse(n.enviar("hola"))
        salida = "\n".join(cm.output)
        self.assertNotIn(TOKEN, salida)   # token depurado
        self.assertNotIn(CHAT, salida)    # chat_id depurado
        self.assertIn("***", salida)


if __name__ == "__main__":
    unittest.main()
