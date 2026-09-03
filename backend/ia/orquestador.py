"""
Orquestador del asistente: pregunta → SQL → datos → texto verificado.

Emite un evento por etapa para que la interfaz muestre en qué va, y termina con
un evento ``final`` que trae el texto, la tabla, la gráfica sugerida y la SQL que
respalda todo. Si la consulta falla, se le pide **una** corrección a Cortex
Analyst informándole el error exacto de Snowflake.
"""
from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Iterator
from typing import Any

import pandas as pd

from backend.config import (
    ALLOWED_SCHEMAS,
    APP_VERSION,
    CORTEX_MODEL,
    IA_ADVERTENCIA,
    IA_HISTORY_TURNS,
    IA_MAX_QUESTION_CHARS,
    IA_MAX_ROWS,
    IA_MAX_ROWS_CLIENT,
)
from backend.database import redactar as redactar_secreto
from backend.ia import graficos
from backend.ia.analyst import ClienteAnalyst, ErrorAnalyst, RespuestaAnalyst
from backend.ia.guardas import validar_sql, verificar_cifras
from backend.ia.redactor import redactar as redactar_texto

logger = logging.getLogger("tejido.ia")


def _valor(dato: Any) -> Any:
    """Convierte lo que devuelve pandas a algo que se pueda serializar a JSON."""
    if dato is None or (isinstance(dato, float) and pd.isna(dato)):
        return None
    if isinstance(dato, (pd.Timestamp,)):
        return dato.isoformat()
    if hasattr(dato, "item"):
        try:
            return dato.item()
        except (ValueError, AttributeError):
            return str(dato)
    return dato


class Orquestador:
    """Coordina Cortex Analyst, las guardas, la ejecución y la redacción."""

    def __init__(self, servicio: Any, cliente: ClienteAnalyst | None = None) -> None:
        self._servicio = servicio
        self._cliente = cliente or ClienteAnalyst()

    # ── Historial ────────────────────────────────────────────────────────
    def _historial(self, turnos: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
        """Últimos turnos de la conversación, en el formato del servicio."""
        limpio: list[dict[str, Any]] = []
        for turno in (turnos or [])[-IA_HISTORY_TURNS:]:
            papel = turno.get("role")
            contenido = turno.get("content")
            if papel in {"user", "analyst"} and isinstance(contenido, list):
                limpio.append({"role": papel, "content": contenido})
        return limpio

    def _historial_con_error(
        self, historial: list[dict[str, Any]], respuesta: RespuestaAnalyst, error: str
    ) -> list[dict[str, Any]]:
        """Le devuelve al modelo su propia SQL y el error, para que la corrija."""
        nuevo = list(historial)
        nuevo.append(
            {"role": "analyst", "content": respuesta.contenido_crudo or [{"type": "text", "text": respuesta.interpretacion}]}
        )
        nuevo.append(
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "La consulta anterior falló al ejecutarse con este error exacto: "
                            f"{error[:400]}. Corrígela y devuelve una sola consulta válida."
                        ),
                    }
                ],
            }
        )
        return nuevo

    # ── Flujo principal ──────────────────────────────────────────────────
    def procesar(
        self, pregunta: str, historial: list[dict[str, Any]] | None = None
    ) -> Iterator[dict[str, Any]]:
        """Genera los eventos del flujo completo para una pregunta.

        Yields:
            Diccionarios con ``tipo`` en {``etapa``, ``error``, ``final``}.
        """
        consulta_id = uuid.uuid4().hex[:12]
        inicio = time.monotonic()
        pregunta = (pregunta or "").strip()

        if not pregunta:
            yield self._error(consulta_id, "Escriba una pregunta para comenzar.")
            return
        if len(pregunta) > IA_MAX_QUESTION_CHARS:
            yield self._error(
                consulta_id,
                f"La pregunta supera los {IA_MAX_QUESTION_CHARS} caracteres. Divídala en dos más concretas.",
            )
            return

        turnos = self._historial(historial)
        try:
            # 1 · Cortex Analyst propone la consulta ------------------------
            yield self._etapa(consulta_id, "interpretando", "Interpretando la pregunta…")
            t_analyst = time.monotonic()
            respuesta = self._cliente.preguntar(pregunta, turnos)
            ms_analyst = int((time.monotonic() - t_analyst) * 1000)

            if not respuesta.sql:
                texto = respuesta.interpretacion or (
                    "No logré convertir esa pregunta en una consulta sobre la base. Intente ser más "
                    "concreto: mencione qué quiere contar o sumar y por cuál criterio agruparlo."
                )
                yield self._final(
                    consulta_id,
                    texto=texto,
                    sql="",
                    columnas=[],
                    filas=[],
                    n_filas=0,
                    truncado=False,
                    grafica=None,
                    sugerencias=respuesta.sugerencias,
                    ms_analyst=ms_analyst,
                    ms_sql=0,
                    modelo="",
                    degradado=False,
                    cifras_ok=True,
                    inicio=inicio,
                )
                return

            # 2 · Las guardas deciden si esa consulta se ejecuta ------------
            yield self._etapa(consulta_id, "validando", "Revisando que la consulta sea de solo lectura…")
            validada = validar_sql(respuesta.sql, ALLOWED_SCHEMAS, IA_MAX_ROWS)
            if not validada.ok:
                logger.warning("SQL rechazada por las guardas: %s", validada.motivo)
                yield self._error(
                    consulta_id,
                    f"La consulta generada no pasó la revisión de seguridad: {validada.motivo} "
                    "Reformule la pregunta.",
                )
                return
            yield self._etapa(consulta_id, "consultando", "Consultando la base en Snowflake…", sql=validada.sql)

            # 3 · Ejecución, con una corrección si Snowflake la rechaza -----
            t_sql = time.monotonic()
            marco, error = self._ejecutar(validada.sql)
            sql_final = validada.sql
            if marco is None:
                yield self._etapa(consulta_id, "corrigiendo", "La consulta falló; pidiendo una corrección…")
                try:
                    segunda = self._cliente.preguntar(pregunta, self._historial_con_error(turnos, respuesta, error))
                except ErrorAnalyst as exc:
                    segunda = RespuestaAnalyst()
                    error = f"{error} | al corregir: {exc}"
                if segunda.sql:
                    validada2 = validar_sql(segunda.sql, ALLOWED_SCHEMAS, IA_MAX_ROWS)
                    if validada2.ok:
                        sql_final = validada2.sql
                        yield self._etapa(consulta_id, "consultando", "Reintentando con la consulta corregida…", sql=sql_final)
                        marco, error = self._ejecutar(sql_final)
            ms_sql = int((time.monotonic() - t_sql) * 1000)

            if marco is None:
                yield self._error(
                    consulta_id,
                    f"Snowflake no pudo ejecutar la consulta: {redactar_secreto(error)[:300]}",
                )
                return

            columnas = [str(columna) for columna in marco.columns]
            filas = [[_valor(dato) for dato in fila] for fila in marco.itertuples(index=False, name=None)]
            n_filas = len(filas)
            truncado = n_filas >= IA_MAX_ROWS
            yield self._etapa(
                consulta_id,
                "datos",
                f"{n_filas} fila(s) obtenidas en {ms_sql} ms.",
            )

            # 4 · Redacción dentro de Snowflake ----------------------------
            yield self._etapa(consulta_id, "redactando", "Redactando la respuesta…")
            t_redaccion = time.monotonic()
            redaccion = redactar_texto(
                self._servicio.filas_con_parametros,
                pregunta,
                columnas,
                filas,
                n_filas,
                truncado,
                CORTEX_MODEL,
            )
            ms_redaccion = int((time.monotonic() - t_redaccion) * 1000)

            # 5 · Ninguna cifra sin respaldo -------------------------------
            verificacion = verificar_cifras(redaccion.texto, filas, n_filas, pregunta)
            if not verificacion.ok:
                logger.warning(
                    "Cifras sin respaldo en la redacción (%s); se entrega el resumen de los datos.",
                    verificacion.huerfanas[:5],
                )
                from backend.ia.redactor import resumen_determinista

                redaccion.texto = resumen_determinista(columnas, filas, n_filas, truncado)
                redaccion.modelo, redaccion.degradado = "", True

            self._auditar(pregunta, sql_final, n_filas)
            yield self._final(
                consulta_id,
                texto=redaccion.texto,
                sql=sql_final,
                columnas=columnas,
                filas=filas[:IA_MAX_ROWS_CLIENT],
                n_filas=n_filas,
                truncado=truncado or n_filas > IA_MAX_ROWS_CLIENT,
                grafica=graficos.sugerir(columnas, filas),
                sugerencias=respuesta.sugerencias,
                ms_analyst=ms_analyst,
                ms_sql=ms_sql,
                ms_redaccion=ms_redaccion,
                modelo=redaccion.modelo,
                degradado=redaccion.degradado,
                cifras_ok=verificacion.ok,
                inicio=inicio,
            )
        except ErrorAnalyst as exc:
            logger.warning("Cortex Analyst no respondió: %s", exc)
            yield self._error(consulta_id, str(exc))
        except Exception as exc:  # noqa: BLE001 - frontera del servicio
            logger.exception("Fallo inesperado del asistente")
            yield self._error(
                consulta_id,
                f"El asistente encontró un error inesperado: {redactar_secreto(exc)[:200]}",
            )

    # ── Auxiliares ───────────────────────────────────────────────────────
    def _ejecutar(self, sql: str) -> tuple[pd.DataFrame | None, str]:
        try:
            return self._servicio.dataframe(sql), ""
        except Exception as exc:  # noqa: BLE001 - el texto viaja a la corrección
            return None, str(exc)

    def _auditar(self, pregunta: str, sql: str, n_filas: int) -> None:
        try:
            self._servicio.log_event("Asistente", "Asistente IA", f"{n_filas} filas", pregunta[:900])
        except Exception:  # noqa: BLE001 - la auditoría nunca rompe el flujo
            return

    def _etapa(self, consulta_id: str, etapa: str, detalle: str, **extra: Any) -> dict[str, Any]:
        return {"tipo": "etapa", "consulta_id": consulta_id, "etapa": etapa, "detalle": detalle, **extra}

    def _error(self, consulta_id: str, mensaje: str) -> dict[str, Any]:
        return {"tipo": "error", "consulta_id": consulta_id, "mensaje": mensaje}

    def _final(self, consulta_id: str, *, inicio: float, **datos: Any) -> dict[str, Any]:
        meta = {
            "modelo": datos.pop("modelo", ""),
            "degradado": datos.pop("degradado", False),
            "cifras_verificadas": datos.pop("cifras_ok", True),
            "ms_interpretacion": datos.pop("ms_analyst", 0),
            "ms_consulta": datos.pop("ms_sql", 0),
            "ms_redaccion": datos.pop("ms_redaccion", 0),
            "ms_total": int((time.monotonic() - inicio) * 1000),
            "version": APP_VERSION,
            "vista_semantica": self._cliente.vista_semantica,
        }
        return {
            "tipo": "final",
            "consulta_id": consulta_id,
            "advertencia": IA_ADVERTENCIA,
            "meta": meta,
            **datos,
        }
