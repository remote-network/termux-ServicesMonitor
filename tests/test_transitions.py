import unittest

from _fakes import *  # noqa: F401,F403  (ajusta sys.path)
import services_monitor as sm


def resultado(ok):
    return sm.Resultado("s", "https://x.test", ok, 200 if ok else 500,
                        1.0, "HTTP 200" if ok else "HTTP 500", "2026-01-01 00:00:00")


class TestGraciaYTransiciones(unittest.TestCase):
    def setUp(self):
        self.srv = sm.ServicioConfig(nombre="s", url="https://x.test",
                                     umbral_fallos=2, umbral_exitos=1)
        self.estado = None

    def paso(self, ok):
        self.estado, alerta = sm.evaluar(self.estado, resultado(ok), self.srv)
        return alerta

    def test_baseline_no_alerta(self):
        self.assertIsNone(self.paso(True))               # primer éxito = baseline UP
        self.assertEqual(self.estado["confirmado"], "up")

    def test_gracia_evita_falso_positivo(self):
        self.paso(True)                                  # baseline UP
        self.assertIsNone(self.paso(False))              # 1 fallo: aún UP (gracia)
        self.assertEqual(self.estado["confirmado"], "up")

    def test_caida_confirmada_alerta_una_vez(self):
        self.paso(True)                                  # baseline UP
        self.paso(False)                                 # 1 fallo
        alerta = self.paso(False)                        # 2 fallos -> DOWN
        self.assertIsNotNone(alerta)
        self.assertIn("INACTIVO", alerta)
        # Sigue caído: NO se re-alerta (sin duplicados).
        self.assertIsNone(self.paso(False))
        self.assertEqual(self.estado["confirmado"], "down")

    def test_recuperacion_alerta(self):
        for _ in range(3):
            self.paso(True)
        self.paso(False)
        self.paso(False)                                 # DOWN
        alerta = self.paso(True)                         # umbral_exitos=1 -> UP
        self.assertIsNotNone(alerta)
        self.assertIn("ACTIVO", alerta)

    def test_baseline_caido_no_alerta(self):
        # Si arranca caído, no alerta por servicio (de eso informa el resumen).
        self.paso(False)
        alerta = self.paso(False)                        # confirma DOWN desde None
        self.assertIsNone(alerta)
        self.assertEqual(self.estado["confirmado"], "down")


if __name__ == "__main__":
    unittest.main()
