"""
Asistente de análisis (Snowflake Cortex): estado, pregunta por SSE y descargas.

El asistente vive detrás de las mismas credenciales que el resto del
aplicativo: la SQL la propone Cortex Analyst, pero la valida y la ejecuta este
backend con el rol de siempre, que sólo lee los datos empresariales y escribe
auditoría. Las descargas salen del resultado que el servidor conserva por
``consulta_id`` (todas las filas), nunca de una tabla enviada por el navegador.
"""
from __future__ import annotations

import asyncio
import json
import queue
import re
import threading
from typing import Any, AsyncIterator

import pandas as pd
from fastapi import APIRouter, HTTPException
from fastapi import Request as FastAPIRequest
from fastapi.responses import Response, StreamingResponse

from backend import comun, demo
from backend.comun import DEMO_MODE, DEMO_NIT_EXAMPLES, EXPORT_MAX_ROWS, MIME_PPTX, MIME_XLSX, error_consulta, logger, require_connection
from backend.config import (
    ASISTENTE_DOWNLOAD_TABLE,
    ASISTENTE_LOG_TABLE,
    CORTEX_MODEL,
    IA_ADVERTENCIA,
    IA_HISTORY_TURNS,
    IA_MAX_QUESTION_CHARS,
    IA_PREGUNTAS_SUGERIDAS,
    IA_RESULT_TTL,
    NITS_EJEMPLO,
    QUERY_COLUMNS,
    SEMANTIC_VIEW,
)
from backend.exporter import create_export, filename_for
from backend.glossary import load_glossary
from backend.models import DescargaIA, PreguntaIA, SearchRequest
from backend.queries import build_count_query, build_export_query

router = APIRouter()

#: Separador de eventos del protocolo SSE (dos saltos de línea).
SSE_FIN = "\n\n"
#: Cada cuántos segundos se envía un comentario SSE mientras Snowflake trabaja:
#: mantiene viva la conexión a través de los proxies (que cierran las mudas).
SSE_LATIDO_SEGUNDOS = 10.0
_SESION_ID_INVALIDO = re.compile(r"[^A-Za-z0-9_-]")


# Los dos servicios son únicos por proceso y guardan estado (la cola de
# telemetría y los resultados por consulta_id). Se crean bajo candado: con
# `lru_cache`, dos preguntas simultáneas al arrancar podían construir dos
# orquestadores y dejar huérfanos los resultados de uno de ellos.
# Reentrante a propósito: `orquestador_ia` pide la telemetría mientras lo sostiene.
_CANDADO = threading.RLock()
_TELEMETRIA: Any = None
_ORQUESTADOR: Any = None


def telemetria_ia():
    global _TELEMETRIA
    if _TELEMETRIA is None:
        with _CANDADO:
            if _TELEMETRIA is None:
                from backend.ia.telemetria import Telemetria

                _TELEMETRIA = Telemetria(comun.snowflake, ASISTENTE_LOG_TABLE, ASISTENTE_DOWNLOAD_TABLE, activa=not DEMO_MODE)
    return _TELEMETRIA


def orquestador_ia():
    global _ORQUESTADOR
    if _ORQUESTADOR is None:
        with _CANDADO:
            if _ORQUESTADOR is None:
                from backend.ia.orquestador import Orquestador

                _ORQUESTADOR = Orquestador(comun.snowflake, telemetria=telemetria_ia())
    return _ORQUESTADOR


def ia_disponible() -> tuple[bool, str]:
    """¿Se puede usar el asistente? Devuelve (disponible, motivo si no)."""
    if DEMO_MODE:
        return False, (
            "El asistente necesita datos reales: en modo demostración no hay a qué preguntarle. "
            "Quite APP_DEMO_MODE en Railway para activarlo."
        )
    if not comun.snowflake.configured:
        faltantes = ", ".join(comun.snowflake.missing_variables) or "la llave privada"
        return False, f"Falta configuración de Snowflake para el asistente: {faltantes}."
    return True, ""


def _sesion_id(declarada: str, request: FastAPIRequest) -> str:
    """Identificador de la pestaña (cuerpo o cabecera X-Session-Id), saneado."""
    crudo = declarada or request.headers.get("x-session-id", "")
    return _SESION_ID_INVALIDO.sub("", crudo)[:64]


def _sse(evento: dict[str, Any]) -> str:
    return "data: " + json.dumps(evento, ensure_ascii=False, default=str) + SSE_FIN


@router.get("/api/ia/estado")
def ia_estado() -> dict[str, Any]:
    """Si el asistente está disponible y con qué preguntas puede empezarse."""
    disponible, motivo = ia_disponible()
    return {
        "disponible": disponible,
        "motivo": motivo,
        "vista_semantica": SEMANTIC_VIEW,
        "modelo": CORTEX_MODEL,
        "advertencia": IA_ADVERTENCIA,
        "sugerencias": IA_PREGUNTAS_SUGERIDAS,
        "max_caracteres": IA_MAX_QUESTION_CHARS,
        "nit_ejemplo": DEMO_NIT_EXAMPLES if DEMO_MODE else NITS_EJEMPLO,
        "memoria_turnos": max(1, IA_HISTORY_TURNS // 2),
        "resultado_minutos": max(1, IA_RESULT_TTL // 60),
    }


@router.post("/api/ia/preguntar")
async def ia_preguntar(entrada: PreguntaIA, request: FastAPIRequest) -> StreamingResponse:
    """Procesa la pregunta y transmite el avance por etapas (SSE).

    El orquestador corre en un hilo y deja sus eventos en una cola; este
    generador los reenvía y, mientras no llega ninguno, manda un latido para que
    la conexión no muera durante una etapa larga. Si el navegador cierra la
    conexión (botón «Detener»), se avisa al orquestador para que no siga con
    etapas que nadie va a leer.
    """
    disponible, motivo = ia_disponible()
    sesion_id = _sesion_id(entrada.sesion_id, request)

    async def flujo() -> AsyncIterator[str]:
        if not disponible:
            yield _sse({"tipo": "error", "mensaje": motivo})
            return
        cola: "queue.Queue[Any]" = queue.Queue()
        cancelado = threading.Event()
        fin = object()

        def trabajar() -> None:
            try:
                eventos = orquestador_ia().procesar(
                    entrada.pregunta, entrada.historial, entrada.consulta_ids, sesion_id, cancelado
                )
                for evento in eventos:
                    cola.put(evento)
            except Exception:  # noqa: BLE001 - frontera del servicio
                logger.exception("El asistente falló fuera del orquestador")
                cola.put({"tipo": "error", "mensaje": "El asistente no está disponible en este momento."})
            finally:
                cola.put(fin)

        threading.Thread(target=trabajar, name="asistente", daemon=True).start()
        try:
            while True:
                try:
                    evento = await asyncio.to_thread(cola.get, True, SSE_LATIDO_SEGUNDOS)
                except queue.Empty:
                    yield ": latido" + SSE_FIN
                    continue
                if evento is fin:
                    break
                yield _sse(evento)
        finally:
            cancelado.set()

    return StreamingResponse(
        flujo(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )


def _resultado_guardado(consulta_id: str):
    """El resultado completo que el servidor conserva para esa consulta, o 404 legible."""
    guardado = orquestador_ia().almacen.obtener(consulta_id)
    if guardado is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"El resultado ya no está disponible en el servidor (se conserva {max(1, IA_RESULT_TTL // 60)} "
                "minutos). Vuelva a hacer la pregunta y descargue de nuevo."
            ),
        )
    return guardado


def _texto_para_archivo(guardado) -> str:
    if guardado.texto:
        return guardado.texto
    # Desde 3.5.2 el resumen se guarda con el resultado, así que este respaldo
    # sólo aplica a un resultado anterior que siga en memoria tras un redespliegue.
    return "La tabla y la consulta de este archivo son las que se ejecutaron."


def _descarga_ia(contenido: bytes, nombre: str, tipo: str) -> Response:
    return comun.respuesta_archivo(contenido, nombre, tipo)


@router.post("/api/ia/exportar/excel")
def ia_exportar_excel(entrada: DescargaIA, request: FastAPIRequest) -> Response:
    """Libro de Excel con la respuesta, la tabla completa y la advertencia de IA."""
    from backend.ia.exportadores import crear_excel, nombre_excel

    guardado = _resultado_guardado(entrada.consulta_id)
    try:
        contenido = crear_excel(
            guardado.pregunta, _texto_para_archivo(guardado), guardado.sql, guardado.columnas, guardado.filas, guardado.n_filas
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("No fue posible construir el Excel del asistente")
        raise HTTPException(status_code=500, detail="No fue posible preparar el archivo de Excel.") from exc
    telemetria_ia().registrar_descarga(guardado.consulta_id, _sesion_id(entrada.sesion_id, request), "excel", guardado.n_filas)
    return _descarga_ia(contenido, nombre_excel(guardado.pregunta), MIME_XLSX)


@router.post("/api/ia/exportar/pptx")
def ia_exportar_pptx(entrada: DescargaIA, request: FastAPIRequest) -> Response:
    """Presentación de PowerPoint con la respuesta, la tabla y la advertencia."""
    from backend.ia.exportadores import crear_pptx, nombre_pptx

    guardado = _resultado_guardado(entrada.consulta_id)
    try:
        contenido = crear_pptx(
            guardado.pregunta, _texto_para_archivo(guardado), guardado.sql, guardado.columnas, guardado.filas, guardado.n_filas
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("No fue posible construir la presentación del asistente")
        raise HTTPException(status_code=500, detail="No fue posible preparar la presentación.") from exc
    telemetria_ia().registrar_descarga(guardado.consulta_id, _sesion_id(entrada.sesion_id, request), "pptx", guardado.n_filas)
    return _descarga_ia(contenido, nombre_pptx(guardado.pregunta), MIME_PPTX)


@router.post("/api/ia/exportar/empresas")
def ia_exportar_empresas(entrada: DescargaIA, request: FastAPIRequest) -> StreamingResponse:
    """Listado del asistente con el formato estándar de la sección de consulta.

    Toma los NIT del resultado guardado y recorre el mismo camino que la
    descarga de /consultar (`batch_nits` → consulta de exportación →
    `create_export`), de modo que el libro es el de siempre —Resumen ·
    Vista_Principal · Datos_Completos · Diccionario— con la pregunta, la
    consulta del asistente y la advertencia de IA en la hoja Resumen.
    """
    guardado = _resultado_guardado(entrada.consulta_id)
    if not guardado.nits:
        raise HTTPException(
            status_code=422,
            detail="Este resultado no es un listado de empresas: no trae una columna NIT con la que armar el archivo estándar.",
        )
    nits = guardado.nits[: min(EXPORT_MAX_ROWS, 5000)]
    solicitud = SearchRequest(mode="batch_nits", nits=nits)
    try:
        if DEMO_MODE:
            frame = demo.all_rows(solicitud, EXPORT_MAX_ROWS)
            total = len(frame)
        else:
            require_connection()
            total = comun.snowflake.scalar(build_count_query(solicitud))
            frame = (
                comun.snowflake.dataframe(build_export_query(solicitud, EXPORT_MAX_ROWS))
                if total
                else pd.DataFrame(columns=list(QUERY_COLUMNS.values()))
            )
        if frame.empty:
            raise HTTPException(status_code=404, detail="Ninguno de los NIT de la respuesta se encontró en la base de empresas.")
        frame = comun.drop_contact_columns(frame)
        # La tabla tiene una fila por sede: los NIT encontrados se cuentan sobre
        # valores distintos, no sobre filas, y el archivo declara lo que contiene.
        encontrados = int(frame["NIT"].astype(str).nunique()) if "NIT" in frame.columns else len(frame)
        notas: list[tuple[str, Any]] = [
            ("Origen", "Asistente de análisis (respuesta generada con inteligencia artificial)"),
            ("Pregunta al asistente", guardado.pregunta),
            ("Consulta ejecutada por el asistente", guardado.sql[:1500]),
            ("NIT distintos en la respuesta del asistente", len(guardado.nits)),
            ("NIT encontrados en la base de empresas", encontrados),
            ("Registros incluidos en el archivo", len(frame)),
        ]
        if len(guardado.nits) > len(nits):
            notas.append(("Nota", f"La respuesta tenía {len(guardado.nits)} NIT; el archivo incluye los primeros {len(nits)} (tope por archivo)."))
        if encontrados < len(nits):
            notas.append(("Nota", f"{len(nits) - encontrados} NIT de la respuesta no se encontraron en la base de empresas."))
        if total > len(frame):
            notas.append((
                "Nota",
                f"Los NIT seleccionados tienen {total} registros en la base (una fila por sede) y el archivo "
                f"incluye los primeros {len(frame)}, que es el tope por archivo.",
            ))
        exportadas = len(frame)
        buffer = create_export(frame, solicitud, total, load_glossary()["entries"], notas=notas, aviso=IA_ADVERTENCIA)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("El listado del asistente falló")
        raise HTTPException(status_code=502, detail=error_consulta("No fue posible preparar el listado de empresas.")) from exc
    telemetria_ia().registrar_descarga(guardado.consulta_id, _sesion_id(entrada.sesion_id, request), "empresas", exportadas)
    return comun.respuesta_archivo(buffer, filename_for(solicitud, exportadas, prefijo="Asistente"), MIME_XLSX)
