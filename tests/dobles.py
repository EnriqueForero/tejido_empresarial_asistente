"""
Dobles del asistente compartidos por las pruebas.

Vive en un módulo propio —y no dentro de un archivo `test_*.py`— porque un
archivo de pruebas no es importable de forma fiable desde otro: pytest los carga
como módulos de primer nivel y el nombre `tests.test_x` sólo existe si la raíz
del proyecto quedó en la ruta de módulos. Eso pasó al publicar 3.5.0 en Colab:
en el equipo local funcionaba y allá no.

`pyproject.toml` añade la raíz y esta carpeta a `pythonpath`, de modo que
`from dobles import …` funciona con cualquier directorio de trabajo y con
`pytest` o `python -m pytest`. Al no llamarse `test_*.py`, pytest no lo recoge
como pruebas.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from backend.ia.analyst import RespuestaAnalyst

#: Tabla de empresas, calificada como la exigen las guardas.
TABLA = "APP_SEGMENTACION_EXPORTACIONES.SEGMENTACION.TEJIDO_EMPRESARIAL_COMPLETO_BASE_MUNICIPIOS_P"


class ServicioFalso:
    """Doble de `SnowflakeService`: una tabla fija, y el fallo que se le pida.

    Args:
        marco: Resultado de `dataframe`. Por defecto, una fila con un departamento.
        error: Si se indica, `dataframe` lo lanza (simula un fallo de la consulta).
        redaccion: Texto que devuelve Cortex COMPLETE, o la excepción que lanza.
    """

    def __init__(self, marco: pd.DataFrame | None = None, error: str = "", redaccion: Any = None) -> None:
        self._marco = marco if marco is not None else pd.DataFrame({"DEPARTAMENTO_EMP": ["Antioquia"], "EMPRESAS": [231544]})
        self._error = error
        self._redaccion = redaccion
        self.llamadas_complete = 0
        self.auditado: list[tuple[str, ...]] = []

    def dataframe(self, sql: str) -> pd.DataFrame:
        if self._error:
            raise RuntimeError(self._error)
        return self._marco

    def filas_con_parametros(self, query: str, parametros: list[Any], silencioso: bool = False) -> list[Any]:
        self.llamadas_complete += 1
        if isinstance(self._redaccion, Exception):
            raise self._redaccion
        return [[self._redaccion or "Antioquia concentra 231.544 empresas."]]

    def log_event(self, *args: str) -> None:
        self.auditado.append(tuple(args))


class AnalystFalso:
    """Doble de `ClienteAnalyst`: devuelve una SQL fija y guarda el historial recibido."""

    def __init__(self, sql: str = "", texto: str = "", error: Exception | None = None) -> None:
        self._sql, self._texto, self._error = sql, texto, error
        self.historiales: list[list[dict[str, Any]]] = []
        self.vista_semantica = "VISTA"

    def preguntar(self, pregunta: str, historial=None) -> RespuestaAnalyst:
        self.historiales.append(list(historial or []))
        if self._error:
            raise self._error
        return RespuestaAnalyst(
            sql=self._sql,
            interpretacion=self._texto,
            request_id="req-1",
            contenido_crudo=[{"type": "sql", "statement": self._sql}] if self._sql else [],
        )


class TelemetriaFalsa:
    """Doble de la telemetría: guarda en memoria lo que se habría insertado."""

    def __init__(self) -> None:
        self.registros: list[dict[str, Any]] = []

    def registrar_consulta(self, registro: dict[str, Any]) -> bool:
        self.registros.append(dict(registro))
        return True


class ServicioTelemetriaFalso:
    """Doble para la telemetría real: registra los INSERT o falla siempre."""

    def __init__(self, falla: bool = False) -> None:
        self.inserciones: list[tuple[str, list[Any]]] = []
        self._falla = falla

    def filas_con_parametros(self, query: str, parametros: list[Any], silencioso: bool = False) -> list[Any]:
        if self._falla:
            raise RuntimeError("Object 'ASISTENTE_CONSULTAS' does not exist")
        assert silencioso is True
        self.inserciones.append((query, parametros))
        return []


def correr(servicio, analyst, pregunta: str = "¿Cuántas empresas hay en Antioquia?", **extra):
    """Ejecuta el orquestador completo con los dobles.

    Returns:
        (eventos, telemetría, orquestador).
    """
    from backend.ia.orquestador import Orquestador

    telemetria = TelemetriaFalsa()
    orquestador = Orquestador(servicio, analyst, telemetria=telemetria)
    eventos = list(orquestador.procesar(pregunta, **extra))
    return eventos, telemetria, orquestador
