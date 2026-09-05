"""Metadatos, filtros dependientes, consulta de empresas, ficha y descarga estándar."""
from __future__ import annotations

from typing import Any

import pandas as pd
from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import StreamingResponse

from backend import comun, demo
from backend.comun import (
    DEMO_MODE,
    DEMO_NIT_EXAMPLES,
    EXPORT_MAX_ROWS,
    MIME_XLSX,
    PREVIEW_MAX_ROWS,
    error_consulta,
    logger,
    records,
    require_connection,
)
from backend.config import (
    APP_TITLE,
    APP_VERSION,
    COLUMN_SECTIONS,
    CONTACT_COLUMNS,
    DATA_SOURCES,
    EXPORT_FILTERS,
    EXPORT_INCLUDE_CONTACT_FIELDS,
    FILTER_GROUP_ORDER,
    GENERAL_FILTERS,
    METHOD_NOTES,
    NITS_EJEMPLO,
    PERIODS,
    PREVIEW_COLUMNS,
    QUERY_COLUMNS,
)
from backend.exporter import create_export, filename_for
from backend.glossary import load_glossary
from backend.models import FilterOptionsRequest, SearchRequest, clean_nit
from backend.queries import build_company_query, build_count_query, build_export_query, build_preview_query

router = APIRouter()


@router.get("/api/metadata")
def metadata() -> dict[str, Any]:
    export_columns = [column for column in QUERY_COLUMNS.values() if EXPORT_INCLUDE_CONTACT_FIELDS or column not in CONTACT_COLUMNS]
    return {
        "title": APP_TITLE,
        "version": APP_VERSION,
        "demo": DEMO_MODE,
        "data_connection": "demo" if DEMO_MODE else ("configured" if comun.snowflake.configured else "missing_configuration"),
        "preview_columns": PREVIEW_COLUMNS,
        "export_columns": export_columns,
        "column_sections": [{"title": title, "columns": [c for c in columns if c in export_columns]} for title, columns in COLUMN_SECTIONS],
        "sources": DATA_SOURCES,
        "periods": PERIODS,
        "notes": METHOD_NOTES,
        "filters": [*GENERAL_FILTERS, *EXPORT_FILTERS],
        "filter_groups": FILTER_GROUP_ORDER,
        "export_max_rows": EXPORT_MAX_ROWS,
        "preview_max_rows": PREVIEW_MAX_ROWS,
        "batch_max_nits": 5000,
        "contact_fields_included": EXPORT_INCLUDE_CONTACT_FIELDS,
        "nit_examples": DEMO_NIT_EXAMPLES if DEMO_MODE else NITS_EJEMPLO,
    }


@router.post("/api/filters/options")
def filter_options(request: FilterOptionsRequest) -> dict[str, Any]:
    if DEMO_MODE:
        return demo.filter_options(request.selections)
    require_connection()
    try:
        general = comun.options_for(GENERAL_FILTERS, comun.cached_filter_frame("general"), request.selections)
        exports = comun.options_for(EXPORT_FILTERS, comun.cached_filter_frame("export"), request.selections)
        return {"filters": [*general, *exports], "demo": False}
    except Exception as exc:  # noqa: BLE001
        logger.exception("No fue posible cargar los filtros")
        raise HTTPException(status_code=502, detail=error_consulta("No fue posible cargar los filtros.")) from exc


@router.post("/api/companies/search")
def search_companies(request: SearchRequest, background: BackgroundTasks) -> dict[str, Any]:
    try:
        if DEMO_MODE:
            frame, total = demo.search(request)
        else:
            require_connection()
            total = comun.snowflake.scalar(build_count_query(request))
            frame = comun.snowflake.dataframe(build_preview_query(request)) if total else pd.DataFrame(columns=list(QUERY_COLUMNS.values()))
            background.add_task(comun.log_event, "Búsqueda", f"Consulta {request.mode}", request.model_dump_json())
        columns = [column for column in PREVIEW_COLUMNS if column in frame.columns]
        preview = frame[columns] if columns else frame.iloc[:, 0:0]
        raw_page_count = (total + request.page_size - 1) // request.page_size if total else 0
        max_pages = max(1, PREVIEW_MAX_ROWS // request.page_size)
        return {
            "total": total,
            "page": request.page,
            "page_size": request.page_size,
            "page_count": min(raw_page_count, max_pages),
            "preview_truncated": raw_page_count > max_pages,
            "columns": columns,
            "rows": records(preview),
            "summary": request.summary(),
            "demo": DEMO_MODE,
        }
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("La consulta falló")
        raise HTTPException(status_code=502, detail=error_consulta("La consulta no pudo completarse.")) from exc


@router.get("/api/companies/{nit}")
def company_detail(nit: str, background: BackgroundTasks) -> dict[str, Any]:
    clean = clean_nit(nit)
    if not 2 <= len(clean) <= 12:
        raise HTTPException(status_code=422, detail="El NIT debe tener entre 2 y 12 dígitos.")
    try:
        if DEMO_MODE:
            frame = demo.company(clean)
        else:
            require_connection()
            frame = comun.snowflake.dataframe(build_company_query(clean))
            background.add_task(comun.log_event, "Consulta", "Ficha de empresa", f'{{"nit": "{clean}"}}')
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("La ficha falló")
        raise HTTPException(status_code=502, detail=error_consulta("No fue posible consultar la ficha de la empresa.")) from exc
    if frame.empty:
        raise HTTPException(status_code=404, detail="No encontramos una empresa con ese NIT.")
    frame = comun.drop_contact_columns(frame)
    record = records(frame.head(1))[0]
    sections = []
    placed: set[str] = set()
    for title, columns in COLUMN_SECTIONS:
        fields = [{"name": column, "value": record.get(column)} for column in columns if column in record]
        placed.update(column for column in columns if column in record)
        if fields:
            sections.append({"title": title, "fields": fields})
    leftovers = [{"name": column, "value": value} for column, value in record.items() if column not in placed]
    if leftovers:
        sections.append({"title": "Otras variables", "fields": leftovers})
    return {"nit": clean, "record": record, "sections": sections, "matches": int(len(frame)), "demo": DEMO_MODE}


@router.post("/api/companies/export")
def export_companies(request: SearchRequest, background: BackgroundTasks) -> StreamingResponse:
    try:
        if DEMO_MODE:
            frame = demo.all_rows(request, EXPORT_MAX_ROWS)
            total = len(frame)
        else:
            require_connection()
            total = comun.snowflake.scalar(build_count_query(request))
            if total > EXPORT_MAX_ROWS:
                raise HTTPException(
                    status_code=413,
                    detail=f"La consulta supera las {EXPORT_MAX_ROWS:,} empresas permitidas por archivo. Agrega filtros antes de descargar.".replace(",", "."),
                )
            frame = comun.snowflake.dataframe(build_export_query(request, EXPORT_MAX_ROWS)) if total else pd.DataFrame(columns=list(QUERY_COLUMNS.values()))
            background.add_task(comun.log_event, "Descarga", "Descarga Excel formateado", request.model_dump_json())
        if frame.empty:
            raise HTTPException(status_code=404, detail="No hay resultados para descargar.")
        frame = comun.drop_contact_columns(frame)
        glossary = load_glossary()["entries"]
        file_buffer = create_export(frame, request, total, glossary)
        return comun.respuesta_archivo(file_buffer, filename_for(request, total), MIME_XLSX)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("La exportación falló")
        raise HTTPException(status_code=502, detail=error_consulta("No fue posible preparar el Excel.")) from exc
