import tempfile
import unittest
from pathlib import Path

from _fakes import *  # noqa: F401,F403  (ajusta sys.path)
import services_monitor as sm


class TestEstado(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.ruta = Path(self.dir.name) / "services_status.json"

    def tearDown(self):
        self.dir.cleanup()

    def test_round_trip(self):
        datos = {"web": {"confirmado": "up", "fallos_consecutivos": 0}}
        sm.guardar_estado(self.ruta, datos)
        self.assertEqual(sm.cargar_estado(self.ruta), datos)

    def test_no_deja_tmp(self):
        sm.guardar_estado(self.ruta, {"a": 1})
        sobrantes = list(self.ruta.parent.glob("*.tmp"))
        self.assertEqual(sobrantes, [])

    def test_inexistente_devuelve_vacio(self):
        self.assertEqual(sm.cargar_estado(self.ruta), {})

    def test_corrupto_se_respalda(self):
        self.ruta.write_text("{ esto no es json", encoding="utf-8")
        resultado = sm.cargar_estado(self.ruta)
        self.assertEqual(resultado, {})                      # no explota
        respaldo = self.ruta.with_suffix(self.ruta.suffix + ".corrupto")
        self.assertTrue(respaldo.exists())                   # se respaldó
        self.assertFalse(self.ruta.exists())                 # se movió

    def test_contenido_no_dict_se_ignora(self):
        self.ruta.write_text("[1, 2, 3]", encoding="utf-8")
        self.assertEqual(sm.cargar_estado(self.ruta), {})


if __name__ == "__main__":
    unittest.main()
