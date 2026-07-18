#!/usr/bin/env python3
"""Monitor HTTP para Termux.

Revisa periódicamente varios servicios web y envía alertas a Telegram cuando
cambian de estado (ACTIVO ↔ INACTIVO). Pensado para correr como servicio
supervisado por termux-services/runit.

Diseño:
- Configuración de servicios separada del código (services.json o env SERVICES_JSON).
- Credenciales por variables de entorno (opcionalmente cargadas de un .env).
- Logging estructurado (INFO/WARNING/ERROR); nunca imprime secretos.
- Reintentos con backoff ante errores de red y período de gracia (umbral de
  fallos/éxitos consecutivos) para evitar falsos positivos y alertas duplicadas.
- Apagado limpio ante SIGINT/SIGTERM (runit) con espera interrumpible.

Sin dependencias más allá de `requests`. Compatible con Python 3.9+.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional

try:
    import requests
except ModuleNotFoundError:  # pragma: no cover - entorno sin dependencia
    print("Falta la dependencia 'requests'. Instala con: "
          "pip install -r requirements.txt", file=sys.stderr)
    raise SystemExit(1)


LOG = logging.getLogger("services_monitor")

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = BASE_DIR / "services.json"
DEFAULT_STATE_PATH = BASE_DIR / "services_status.json"
DEFAULT_ENV_PATH = BASE_DIR / ".env"

METODOS_HTTP_VALIDOS = {"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"}


class ConfigError(Exception):
    """Error de configuración con un mensaje claro para el usuario."""


# ============================================================
# .env (carga con librería estándar, sin python-dotenv)
# ============================================================
def cargar_dotenv(path: Path = DEFAULT_ENV_PATH) -> None:
    """Carga variables de un archivo .env SIN pisar las ya definidas en el entorno.

    Formato: líneas `CLAVE=valor`; ignora vacías y comentarios (#). Las comillas
    envolventes se eliminan. El entorno real tiene prioridad sobre el .env.
    """
    if not path.exists():
        return
    try:
        for linea in path.read_text(encoding="utf-8").splitlines():
            linea = linea.strip()
            if not linea or linea.startswith("#") or "=" not in linea:
                continue
            clave, _, valor = linea.partition("=")
            clave = clave.strip()
            valor = valor.strip().strip('"').strip("'")
            if clave and clave not in os.environ:
                os.environ[clave] = valor
    except OSError as exc:
        LOG.warning("No se pudo leer %s: %s", path, exc)


# ============================================================
# Logging
# ============================================================
def configurar_logging(nivel: str = "INFO") -> None:
    """Configura logging a stdout (lo captura svlogger bajo runit)."""
    nivel_num = getattr(logging, str(nivel).upper(), logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(
        fmt="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    root = logging.getLogger()
    for viejo in list(root.handlers):
        root.removeHandler(viejo)
    root.addHandler(handler)
    root.setLevel(nivel_num)


def ahora() -> str:
    """Fecha y hora local en formato legible."""
    return datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")


# ============================================================
# Modelos de configuración
# ============================================================
@dataclass
class ServicioConfig:
    nombre: str
    url: str
    metodo: str = "GET"
    timeout: float = 10.0
    codigos_validos: tuple[int, ...] = (200,)
    headers: dict[str, str] = field(default_factory=dict)
    contenido_esperado: Optional[str] = None
    umbral_fallos: int = 2
    umbral_exitos: int = 1
    reintentos: int = 2
    backoff_base: float = 1.0


@dataclass
class Ajustes:
    intervalo: int
    servicios: list[ServicioConfig]
    telegram_token: str
    telegram_chat_id: str
    ruta_estado: Path


@dataclass
class Resultado:
    nombre: str
    url: str
    ok: bool
    codigo: Optional[int]
    latencia_ms: float
    detalle: str
    fecha: str


# ============================================================
# Carga y validación de configuración
# ============================================================
def _env_int(nombre: str, defecto: int) -> int:
    valor = os.getenv(nombre)
    if valor is None or valor.strip() == "":
        return defecto
    try:
        return int(valor)
    except ValueError:
        raise ConfigError(f"{nombre} debe ser un entero, recibí: {valor!r}")


def _env_float(nombre: str, defecto: float) -> float:
    valor = os.getenv(nombre)
    if valor is None or valor.strip() == "":
        return defecto
    try:
        return float(valor)
    except ValueError:
        raise ConfigError(f"{nombre} debe ser un número, recibí: {valor!r}")


def construir_servicio(raw: Any, indice: int, defaults: dict[str, Any]) -> ServicioConfig:
    """Valida un servicio (dict) y devuelve un ServicioConfig, o lanza ConfigError."""
    etiqueta = f"servicio #{indice + 1}"
    if not isinstance(raw, dict):
        raise ConfigError(f"{etiqueta}: debe ser un objeto JSON, no {type(raw).__name__}.")

    nombre = raw.get("nombre")
    if not isinstance(nombre, str) or not nombre.strip():
        raise ConfigError(f"{etiqueta}: falta 'nombre' (texto no vacío).")

    url = raw.get("url")
    if not isinstance(url, str) or not url.startswith(("http://", "https://")):
        raise ConfigError(f"servicio '{nombre}': 'url' debe empezar por http:// o https://.")

    metodo = str(raw.get("metodo", "GET")).upper()
    if metodo not in METODOS_HTTP_VALIDOS:
        raise ConfigError(
            f"servicio '{nombre}': método '{metodo}' no válido "
            f"(usa uno de {sorted(METODOS_HTTP_VALIDOS)}).")

    timeout = raw.get("timeout", defaults["timeout"])
    if not isinstance(timeout, (int, float)) or timeout <= 0:
        raise ConfigError(f"servicio '{nombre}': 'timeout' debe ser un número > 0.")

    codigos = raw.get("codigos_validos", [200])
    if (not isinstance(codigos, list) or not codigos
            or not all(isinstance(c, int) for c in codigos)):
        raise ConfigError(
            f"servicio '{nombre}': 'codigos_validos' debe ser una lista no vacía de enteros.")

    headers = raw.get("headers", {})
    if not isinstance(headers, dict) or not all(
            isinstance(k, str) and isinstance(v, str) for k, v in headers.items()):
        raise ConfigError(f"servicio '{nombre}': 'headers' debe ser un objeto de texto→texto.")

    contenido = raw.get("contenido_esperado")
    if contenido is not None and not isinstance(contenido, str):
        raise ConfigError(f"servicio '{nombre}': 'contenido_esperado' debe ser texto.")

    umbral_fallos = raw.get("umbral_fallos", defaults["umbral_fallos"])
    umbral_exitos = raw.get("umbral_exitos", defaults["umbral_exitos"])
    reintentos = raw.get("reintentos", defaults["reintentos"])
    for campo, val in (("umbral_fallos", umbral_fallos), ("umbral_exitos", umbral_exitos),
                       ("reintentos", reintentos)):
        if not isinstance(val, int) or val < 0 or (campo != "reintentos" and val < 1):
            raise ConfigError(f"servicio '{nombre}': '{campo}' debe ser un entero válido.")

    backoff = raw.get("backoff_base", defaults["backoff_base"])
    if not isinstance(backoff, (int, float)) or backoff < 0:
        raise ConfigError(f"servicio '{nombre}': 'backoff_base' debe ser un número >= 0.")

    return ServicioConfig(
        nombre=nombre.strip(),
        url=url,
        metodo=metodo,
        timeout=float(timeout),
        codigos_validos=tuple(codigos),
        headers=dict(headers),
        contenido_esperado=contenido,
        umbral_fallos=int(umbral_fallos),
        umbral_exitos=int(umbral_exitos),
        reintentos=int(reintentos),
        backoff_base=float(backoff),
    )


def construir_servicios(datos: Any, defaults: dict[str, Any]) -> list[ServicioConfig]:
    """Valida la lista completa de servicios (nombres únicos incluidos)."""
    if not isinstance(datos, list) or not datos:
        raise ConfigError("La configuración de servicios debe ser una lista JSON no vacía.")
    servicios: list[ServicioConfig] = []
    vistos: set[str] = set()
    for i, raw in enumerate(datos):
        servicio = construir_servicio(raw, i, defaults)
        if servicio.nombre in vistos:
            raise ConfigError(f"nombre de servicio duplicado: '{servicio.nombre}'.")
        vistos.add(servicio.nombre)
        servicios.append(servicio)
    return servicios


def _leer_datos_servicios() -> Any:
    """Obtiene la lista de servicios cruda desde SERVICES_JSON o el archivo config."""
    inline = os.getenv("SERVICES_JSON")
    if inline and inline.strip():
        try:
            return json.loads(inline)
        except json.JSONDecodeError as exc:
            raise ConfigError(f"SERVICES_JSON no es JSON válido: {exc}")
    ruta = Path(os.getenv("SERVICES_MONITOR_CONFIG", str(DEFAULT_CONFIG_PATH)))
    if not ruta.exists():
        raise ConfigError(
            f"No hay configuración de servicios: crea {ruta.name} "
            "(ver services.example.json) o define SERVICES_JSON.")
    try:
        return json.loads(ruta.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigError(f"{ruta.name} no es JSON válido: {exc}")
    except OSError as exc:
        raise ConfigError(f"No se pudo leer {ruta}: {exc}")


def cargar_ajustes() -> Ajustes:
    """Carga y valida toda la configuración. Lanza ConfigError con mensajes claros."""
    token = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    chat_id = (os.getenv("TELEGRAM_CHAT_ID") or "").strip()
    if not token:
        raise ConfigError("falta TELEGRAM_BOT_TOKEN (defínelo en .env o el entorno).")
    if not chat_id:
        raise ConfigError("falta TELEGRAM_CHAT_ID (defínelo en .env o el entorno).")

    defaults = {
        "timeout": _env_float("HTTP_TIMEOUT", 10.0),
        "umbral_fallos": _env_int("UMBRAL_FALLOS", 2),
        "umbral_exitos": _env_int("UMBRAL_EXITOS", 1),
        "reintentos": _env_int("HTTP_REINTENTOS", 2),
        "backoff_base": _env_float("HTTP_BACKOFF", 1.0),
    }
    intervalo = _env_int("CHECK_INTERVAL", _env_int("INTERVALO_SEGUNDOS", 60))
    if intervalo < 1:
        raise ConfigError("CHECK_INTERVAL debe ser >= 1 segundo.")

    servicios = construir_servicios(_leer_datos_servicios(), defaults)
    ruta_estado = Path(os.getenv("SERVICES_MONITOR_STATE", str(DEFAULT_STATE_PATH)))
    return Ajustes(intervalo, servicios, token, chat_id, ruta_estado)


# ============================================================
# Estado persistente (atómico y tolerante a corrupción)
# ============================================================
def cargar_estado(ruta: Path) -> dict[str, Any]:
    """Carga el estado previo. Si el archivo está corrupto, lo respalda y sigue."""
    if not ruta.exists():
        return {}
    try:
        contenido = json.loads(ruta.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        respaldo = ruta.with_suffix(ruta.suffix + ".corrupto")
        LOG.warning("Estado corrupto (%s); respaldando en %s y empezando de cero.",
                    exc, respaldo.name)
        try:
            ruta.replace(respaldo)
        except OSError:
            pass
        return {}
    except OSError as exc:
        LOG.warning("No se pudo leer el estado (%s); empezando de cero.", exc)
        return {}
    return contenido if isinstance(contenido, dict) else {}


def guardar_estado(ruta: Path, estado: dict[str, Any]) -> None:
    """Escribe el estado de forma atómica (archivo temporal + fsync + replace)."""
    tmp = ruta.with_suffix(ruta.suffix + ".tmp")
    try:
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(estado, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        tmp.replace(ruta)
    except OSError as exc:
        LOG.error("No se pudo guardar el estado: %s", exc)
        try:
            tmp.unlink(missing_ok=True)  # type: ignore[call-arg]
        except (OSError, TypeError):
            pass


# ============================================================
# Comprobación HTTP (con reintentos + backoff en errores de red)
# ============================================================
def _tipo_error(exc: Exception) -> str:
    if isinstance(exc, requests.exceptions.Timeout):
        return "timeout"
    if isinstance(exc, requests.exceptions.ConnectionError):
        return "conexión rechazada o host inaccesible"
    return exc.__class__.__name__


def comprobar_servicio(servicio: ServicioConfig, session: Any,
                       stop: Optional[threading.Event] = None,
                       sleep: Callable[[float], Any] = time.sleep) -> Resultado:
    """Comprueba un servicio. Reintenta con backoff SOLO ante errores de red.

    Una respuesta HTTP (aunque sea 5xx) se evalúa contra codigos_validos y no se
    reintenta. `stop` permite abortar el backoff si el monitor se está apagando.
    """
    intentos = servicio.reintentos + 1
    ultimo_error = "error de red"
    for intento in range(intentos):
        inicio = time.monotonic()
        try:
            resp = session.request(
                servicio.metodo, servicio.url,
                timeout=servicio.timeout,
                headers=servicio.headers or None,
                allow_redirects=True,
            )
        except requests.exceptions.RequestException as exc:
            ultimo_error = _tipo_error(exc)
            if intento < intentos - 1:
                espera = servicio.backoff_base * (2 ** intento)
                LOG.warning("%s: %s (intento %d/%d); reintento en %.1fs",
                            servicio.nombre, ultimo_error, intento + 1, intentos, espera)
                if stop is not None:
                    if stop.wait(espera):
                        break
                else:
                    sleep(espera)
                continue
            latencia = round((time.monotonic() - inicio) * 1000, 1)
            return Resultado(servicio.nombre, servicio.url, False, None, latencia,
                             f"Error de red: {ultimo_error}", ahora())

        latencia = round((time.monotonic() - inicio) * 1000, 1)
        codigo = resp.status_code
        ok = codigo in servicio.codigos_validos
        if not ok:
            detalle = f"HTTP {codigo}; esperados {list(servicio.codigos_validos)}"
        else:
            detalle = f"HTTP {codigo}"
            if servicio.contenido_esperado:
                cuerpo = getattr(resp, "text", "") or ""
                if servicio.contenido_esperado not in cuerpo:
                    ok = False
                    detalle = f"HTTP {codigo}; falta el contenido esperado"
        return Resultado(servicio.nombre, servicio.url, ok, codigo, latencia, detalle, ahora())

    return Resultado(servicio.nombre, servicio.url, False, None, 0.0,
                     "Comprobación interrumpida (apagado)", ahora())


# ============================================================
# Transición de estado con período de gracia
# ============================================================
def evaluar(prev: Optional[dict[str, Any]], resultado: Resultado,
            servicio: ServicioConfig) -> tuple[dict[str, Any], Optional[str]]:
    """Actualiza el estado de un servicio y decide si hay que alertar.

    Reglas:
    - Cuenta fallos/éxitos consecutivos.
    - Un servicio pasa a INACTIVO tras `umbral_fallos` fallos seguidos, y a
      ACTIVO tras `umbral_exitos` éxitos seguidos (período de gracia).
    - Solo se alerta cuando el estado CONFIRMADO cambia; nunca se alerta el
      baseline inicial (confirmado previo desconocido) para evitar ruido al
      arrancar (de eso ya informa el resumen de inicio).
    """
    estado: dict[str, Any] = dict(prev) if prev else {}
    confirmado = estado.get("confirmado")  # "up" | "down" | None

    if resultado.ok:
        estado["exitos_consecutivos"] = int(estado.get("exitos_consecutivos", 0)) + 1
        estado["fallos_consecutivos"] = 0
    else:
        estado["fallos_consecutivos"] = int(estado.get("fallos_consecutivos", 0)) + 1
        estado["exitos_consecutivos"] = 0

    estado["ultimo_codigo"] = resultado.codigo
    estado["ultimo_detalle"] = resultado.detalle
    estado["ultima_revision"] = resultado.fecha

    nuevo = confirmado
    if resultado.ok and estado["exitos_consecutivos"] >= servicio.umbral_exitos:
        nuevo = "up"
    elif not resultado.ok and estado["fallos_consecutivos"] >= servicio.umbral_fallos:
        nuevo = "down"

    alerta: Optional[str] = None
    if nuevo != confirmado:
        estado["confirmado"] = nuevo
        estado["ultimo_cambio"] = resultado.fecha
        if confirmado is not None:  # no alertar el baseline inicial
            alerta = crear_mensaje_estado(resultado, nuevo == "up")
    return estado, alerta


# ============================================================
# Mensajes de Telegram
# ============================================================
def crear_mensaje_estado(resultado: Resultado, activo: bool) -> str:
    icono = "✅" if activo else "🔴"
    estado = "ACTIVO" if activo else "INACTIVO"
    return (
        f"{icono} {resultado.nombre}: {estado}\n"
        f"URL: {resultado.url}\n"
        f"Detalle: {resultado.detalle}\n"
        f"Latencia: {resultado.latencia_ms} ms\n"
        f"Fecha: {resultado.fecha}"
    )


def crear_resumen(resultados: list[Resultado], intervalo: int) -> str:
    lineas = ["📡 Monitor HTTP iniciado", "",
              f"Servicios configurados: {len(resultados)}", ""]
    for r in resultados:
        icono = "✅" if r.ok else "🔴"
        estado = "ACTIVO" if r.ok else "INACTIVO"
        lineas.append(f"{icono} {r.nombre}: {estado} — {r.latencia_ms} ms")
    lineas += ["", f"Intervalo: {intervalo} segundos", f"Fecha: {ahora()}"]
    return "\n".join(lineas)


# ============================================================
# Notificador de Telegram (nunca expone secretos)
# ============================================================
class Notifier:
    def __init__(self, token: str, chat_id: str, session: Any) -> None:
        self._token = token
        self._chat_id = chat_id
        self._session = session

    def _scrub(self, texto: str) -> str:
        """Elimina token/chat_id de cualquier texto antes de logearlo."""
        if self._token:
            texto = texto.replace(self._token, "***")
        if self._chat_id:
            texto = texto.replace(str(self._chat_id), "***")
        return texto

    def enviar(self, mensaje: str) -> bool:
        url = f"https://api.telegram.org/bot{self._token}/sendMessage"
        try:
            resp = self._session.post(
                url,
                json={"chat_id": self._chat_id, "text": mensaje,
                      "disable_web_page_preview": True},
                timeout=20,
            )
            resp.raise_for_status()
            data = resp.json()
            if not data.get("ok"):
                LOG.error("Telegram rechazó el mensaje: %s", self._scrub(str(data)))
                return False
            LOG.info("Alerta enviada a Telegram (%d caracteres).", len(mensaje))
            return True
        except requests.exceptions.RequestException as exc:
            # La excepción puede contener la URL con el token: SIEMPRE se depura.
            LOG.error("No se pudo enviar a Telegram: %s", self._scrub(str(exc)))
            return False
        except ValueError as exc:
            LOG.error("Respuesta inválida de Telegram: %s", self._scrub(str(exc)))
            return False


# ============================================================
# Monitor (bucle + manejo de señales)
# ============================================================
class Monitor:
    def __init__(self, ajustes: Ajustes, session: Any, notifier: Notifier) -> None:
        self.ajustes = ajustes
        self.session = session
        self.notifier = notifier
        self.stop = threading.Event()

    def manejar_senal(self, signum: int, _frame: Any) -> None:
        try:
            nombre = signal.Signals(signum).name
        except ValueError:
            nombre = str(signum)
        LOG.info("Señal %s recibida; deteniendo…", nombre)
        self.stop.set()

    def instalar_senales(self) -> None:
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                signal.signal(sig, self.manejar_senal)
            except (ValueError, OSError):  # pragma: no cover - hilos/plataforma
                pass

    def revisar(self, estados: dict[str, Any]) -> list[Resultado]:
        resultados: list[Resultado] = []
        for servicio in self.ajustes.servicios:
            resultado = comprobar_servicio(servicio, self.session, self.stop)
            resultados.append(resultado)
            prev = estados.get(servicio.nombre)
            nuevo_estado, alerta = evaluar(prev, resultado, servicio)
            estados[servicio.nombre] = nuevo_estado
            LOG.log(logging.INFO if resultado.ok else logging.WARNING,
                    "%s: %s (%s)", servicio.nombre,
                    "ACTIVO" if resultado.ok else "INACTIVO", resultado.detalle)
            if alerta:
                self.notifier.enviar(alerta)
            if self.stop.is_set():
                break
        return resultados

    def run(self, una_vez: bool = False) -> None:
        a = self.ajustes
        LOG.info("Iniciando monitor: %d servicio(s), intervalo %ds.",
                 len(a.servicios), a.intervalo)
        estados = cargar_estado(a.ruta_estado)

        resultados = self.revisar(estados)          # baseline (sin alertas por servicio)
        guardar_estado(a.ruta_estado, estados)
        self.notifier.enviar(crear_resumen(resultados, a.intervalo))

        if una_vez:
            return

        while not self.stop.is_set():
            if self.stop.wait(a.intervalo):         # espera interrumpible por señal
                break
            self.revisar(estados)
            guardar_estado(a.ruta_estado, estados)

        self.notifier.enviar(f"🛑 Monitor HTTP detenido\nFecha: {ahora()}")
        LOG.info("Monitor detenido limpiamente.")


# ============================================================
# CLI / arranque
# ============================================================
def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Monitor HTTP para Termux con alertas a Telegram.")
    p.add_argument("--check-config", action="store_true",
                   help="valida la configuración y sale (no hace red).")
    p.add_argument("--once", action="store_true",
                   help="ejecuta una sola ronda de comprobaciones y sale.")
    return p.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    cargar_dotenv()
    configurar_logging(os.getenv("LOG_LEVEL", "INFO"))

    try:
        ajustes = cargar_ajustes()
    except ConfigError as exc:
        LOG.error("Configuración inválida: %s", exc)
        return 2

    if args.check_config:
        LOG.info("Configuración válida: %d servicio(s), intervalo %ds.",
                 len(ajustes.servicios), ajustes.intervalo)
        return 0

    session = requests.Session()
    notifier = Notifier(ajustes.telegram_token, ajustes.telegram_chat_id, session)
    monitor = Monitor(ajustes, session, notifier)
    monitor.instalar_senales()
    try:
        monitor.run(una_vez=args.once)
    finally:
        session.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
