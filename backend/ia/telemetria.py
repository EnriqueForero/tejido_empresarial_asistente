"""
Telemetría del asistente: cada pregunta y cada descarga quedan en Snowflake.

Se registra **todo** lo que ocurre —éxito, degradación, rechazo de las guardas,
fallo de Analyst o de la SQL, detención— con los tiempos de cada etapa, para
que se pueda responder «qué se pregunta, cuánto tarda y dónde falla» con una
consulta SQL (ver docs/METRICAS.md).

Diseño: una cola acotada y un hilo consumidor. La inserción usa parámetros
enlazados y **nunca** guarda filas del resultado ni datos de contacto. Si la
tabla no existe o el INSERT falla, se cuenta el descarte y el aplicativo sigue:
la telemetría no puede frenar ni tumbar una respuesta.
"""
from __future__ import annotations

import logging
import queue
import threading
import time
import uuid
from typing import Any

from backend.database import redactar

logger = logging.getLogger("tejido.ia.telemetria")

COLUMNAS_CONSULTA = [
    "CONSULTA_ID", "SESION_ID", "PREGUNTA", "SQL_GENERADA", "SQL_VALIDADA", "RESPUESTA",
    "ESTADO", "EXITO", "DEGRADADO", "MOTIVO_DEGRADACION", "CIFRAS_VERIFICADAS",
    "N_FILAS", "TRUNCADO", "ES_LISTADO", "MOSTRO_GRAFICA",
    "MS_INTERPRETACION", "MS_CONSULTA", "MS_CORRECCION", "MS_REDACCION", "MS_TOTAL",
    "INTENTOS_SQL", "MODELO", "FORMA_REDACCION", "ANALYST_REQUEST_ID", "ETAPA_FALLO", "ERROR",
    "APP_VERSION", "VISTA_SEMANTICA", "ENTORNO",
]
COLUMNAS_DESCARGA = ["DESCARGA_ID", "CONSULTA_ID", "SESION_ID", "FORMATO", "N_FILAS"]

#: Longitud máxima de cada texto, alineada con el DDL (snowflake/03_telemetria_asistente.sql).
_TOPES = {
    "CONSULTA_ID": 12, "SESION_ID": 64, "PREGUNTA": 2000, "SQL_GENERADA": 20000, "SQL_VALIDADA": 20000,
    "RESPUESTA": 4000, "ESTADO": 30, "MOTIVO_DEGRADACION": 60, "MODELO": 80, "FORMA_REDACCION": 20,
    "ANALYST_REQUEST_ID": 80,
    "ETAPA_FALLO": 30, "ERROR": 1000, "APP_VERSION": 20, "VISTA_SEMANTICA": 300, "ENTORNO": 30,
    "DESCARGA_ID": 12, "FORMATO": 20,
}
#: Tras esta cantidad de fallos seguidos se espera antes de volver a intentar,
#: para no golpear Snowflake si la tabla no existe.
_FALLOS_PARA_PAUSA = 5
_PAUSA_SEGUNDOS = 60.0


def _sentencia(tabla: str, columnas: list[str]) -> str:
    marcadores = ", ".join("?" for _ in columnas)
    return f"INSERT INTO {tabla} ({', '.join(columnas)}) VALUES ({marcadores})"


def _valor(columna: str, valor: Any) -> Any:
    if valor is None:
        return None
    if isinstance(valor, bool):
        return valor
    if isinstance(valor, (int, float)):
        return valor
    texto = str(valor)
    tope = _TOPES.get(columna)
    return texto[:tope] if tope else texto


class Telemetria:
    """Registro asíncrono de consultas y descargas del asistente."""

    def __init__(
        self,
        servicio: Any,
        tabla_consultas: str,
        tabla_descargas: str,
        capacidad: int = 500,
        activa: bool = True,
    ) -> None:
        self._servicio = servicio
        self._sql_consulta = _sentencia(tabla_consultas, COLUMNAS_CONSULTA)
        self._sql_descarga = _sentencia(tabla_descargas, COLUMNAS_DESCARGA)
        self._cola: "queue.Queue[tuple[str, list[Any]]]" = queue.Queue(maxsize=max(10, capacidad))
        self._activa = activa
        self._hilo: threading.Thread | None = None
        self._lock = threading.Lock()
        self.registrados = 0
        self.descartados = 0
        self.fallos = 0
        self.fallos_seguidos = 0
        self.ultimo_error = ""

    # ── API ──────────────────────────────────────────────────────────────
    def registrar_consulta(self, registro: dict[str, Any]) -> bool:
        """Encola el registro de una pregunta (cualquier salida del orquestador)."""
        fila = [_valor(columna, registro.get(columna.lower())) for columna in COLUMNAS_CONSULTA]
        return self._encolar(self._sql_consulta, fila)

    def registrar_descarga(self, consulta_id: str, sesion_id: str, formato: str, n_filas: int) -> bool:
        fila = [uuid.uuid4().hex[:12], consulta_id[:12], (sesion_id or "")[:64], formato[:20], int(n_filas)]
        return self._encolar(self._sql_descarga, fila)

    def estado(self) -> dict[str, Any]:
        """Para /api/diagnostico: cuántos registros entraron y cuántos se perdieron."""
        return {
            "activa": self._activa,
            "pendientes": self._cola.qsize(),
            "registrados": self.registrados,
            "descartados": self.descartados,
            "fallos": self.fallos,
            "ultimo_error": self.ultimo_error,
        }

    def vaciar(self, plazo: float = 5.0) -> None:
        """Espera (hasta `plazo` s) a que se procese lo encolado; útil en pruebas y al apagar.

        Espera a que las tareas estén **terminadas**, no a que la cola esté
        vacía: el consumidor saca el registro antes de insertarlo, así que una
        cola vacía no significa que el INSERT ya ocurrió.
        """
        limite = time.monotonic() + plazo
        with self._cola.all_tasks_done:
            while self._cola.unfinished_tasks and time.monotonic() < limite:
                self._cola.all_tasks_done.wait(timeout=0.05)

    # ── Interno ──────────────────────────────────────────────────────────
    def _encolar(self, sql: str, fila: list[Any]) -> bool:
        if not self._activa:
            return False
        try:
            self._cola.put_nowait((sql, fila))
        except queue.Full:
            self.descartados += 1
            return False
        self._asegurar_hilo()
        return True

    def _asegurar_hilo(self) -> None:
        with self._lock:
            if self._hilo is not None and self._hilo.is_alive():
                return
            self._hilo = threading.Thread(target=self._trabajar, name="telemetria-asistente", daemon=True)
            self._hilo.start()

    def _trabajar(self) -> None:
        while True:
            try:
                sql, fila = self._cola.get(timeout=30)
            except queue.Empty:
                # Sin trabajo: el hilo se retira, pero sólo bajo el candado y tras
                # comprobar que nadie encoló mientras tanto. Si no, `_asegurar_hilo`
                # vería un hilo «vivo» que ya no va a leer la cola.
                with self._lock:
                    if not self._cola.empty():
                        continue
                    self._hilo = None
                    return
            try:
                if self.fallos_seguidos >= _FALLOS_PARA_PAUSA:
                    time.sleep(_PAUSA_SEGUNDOS)
                    self.fallos_seguidos = 0
                self._servicio.filas_con_parametros(sql, fila, silencioso=True)
                self.registrados += 1
                self.fallos_seguidos = 0
            except Exception as exc:  # noqa: BLE001 - la telemetría nunca rompe nada
                self.fallos += 1
                self.fallos_seguidos += 1
                self.descartados += 1
                self.ultimo_error = redactar(exc, 300)
                if self.fallos <= 3 or self.fallos % 50 == 0:
                    logger.warning(
                        "No se pudo registrar telemetría del asistente (%s fallos): %s", self.fallos, self.ultimo_error
                    )
            finally:
                self._cola.task_done()
