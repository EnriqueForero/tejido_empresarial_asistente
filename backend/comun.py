"""
Ajustes de ejecución y utilidades que comparten los routers de la API.

Aquí vive lo que antes estaba disperso en `main.py`: la lectura de las
variables de entorno que gobiernan el proceso (modo demostración, topes,
control de acceso), la conversión de tablas a registros JSON, la regla de
contacto, el catálogo de filtros en memoria y los mensajes de error con causa.

Los routers usan la conexión como ``comun.snowflake`` —y no con un import
directo— para que las pruebas y el servidor simulado puedan sustituirla.
"""
from __future__ import annotations

import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Iterator
from urllib.parse import quote

import pandas as pd
from fastapi import HTTPException
from fastapi.responses import StreamingResponse

from backend.config import CONTACT_COLUMNS, EXPORT_FILTER_TABLE, EXPORT_INCLUDE_CONTACT_FIELDS, GENERAL_FILTER_TABLE
from backend.database import snowflake  # noqa: F401 - se usa como comun.snowflake (sustituible)

logger = logging.getLogger("tejido")

BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIST = BASE_DIR / "frontend" / "dist"

MIME_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
MIME_PPTX = "application/vnd.openxmlformats-officedocument.presentationml.presentation"


def _flag(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


def _integer_env(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)).replace("_", ""))
    except (TypeError, ValueError):
        value = default
    return min(max(value, minimum), maximum)


DEMO_MODE = _flag("APP_DEMO_MODE")
APP_ENV = os.getenv("APP_ENV", "production").strip().lower()
EXPORT_MAX_ROWS = _integer_env("EXPORT_MAX_ROWS", 5000, 1, 20000)
PREVIEW_MAX_ROWS = 10_000
MAX_REQUEST_BYTES = _integer_env("MAX_REQUEST_BYTES", 2_000_000, 50_000, 10_000_000)
PUBLIC_ORIGIN = os.getenv("PUBLIC_ORIGIN", "").rstrip("/")
ACCESS_USER = os.getenv("APP_BASIC_USER", "")
ACCESS_PASSWORD = os.getenv("APP_BASIC_PASSWORD", "")
ACCESS_CONTROL_ACTIVE = bool(ACCESS_USER and ACCESS_PASSWORD)
ACCESS_CONTROL_PARTIAL = bool(ACCESS_USER) != bool(ACCESS_PASSWORD)
# Igual que el aplicativo Streamlit original, el acceso es abierto salvo que se configure
# APP_BASIC_USER y APP_BASIC_PASSWORD. Los campos de contacto se incluyen en la descarga
# como en el original; se retiran con EXPORT_INCLUDE_CONTACT_FIELDS=false (regla en
# backend/config.py, compartida con el asistente).
DIAG_TOKEN = os.getenv("APP_DIAG_TOKEN", "").strip()
#: NIT del modo demostración (empresas sintéticas de backend/demo.py).
DEMO_NIT_EXAMPLES = ["900000001", "900000003", "9000000"]


# ── Datos ───────────────────────────────────────────────────────────────────
def identifier_columns(columns: Iterable[str]) -> list[str]:
    return [column for column in columns if column == "NIT" or column.startswith(("Código ", "Dígito ", "ID "))]


def records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    """Filas de un DataFrame como diccionarios JSON, con los identificadores como texto."""
    clean = frame.astype(object).where(pd.notnull(frame), None)
    for column in identifier_columns(clean.columns):
        clean[column] = clean[column].map(
            lambda value: None
            if value is None
            else str(int(value))
            if isinstance(value, float) and float(value).is_integer()
            else str(value)
        )
    salida = clean.to_dict(orient="records")
    for record in salida:
        for key, value in record.items():
            if hasattr(value, "item"):
                try:
                    record[key] = value.item()
                except (TypeError, ValueError):
                    record[key] = str(value)
    return salida


def drop_contact_columns(frame: pd.DataFrame) -> pd.DataFrame:
    if EXPORT_INCLUDE_CONTACT_FIELDS:
        return frame
    return frame.drop(columns=[column for column in CONTACT_COLUMNS if column in frame.columns])


# Catálogo de valores por filtro: cambia con el corte de datos, no entre
# consultas, así que se guarda en memoria (el original usaba @st.cache_data).
@lru_cache(maxsize=2)
def cached_filter_frame(kind: str) -> pd.DataFrame:
    table = GENERAL_FILTER_TABLE if kind == "general" else EXPORT_FILTER_TABLE
    frame = snowflake.dataframe(f"SELECT * FROM {table}")
    return frame.astype(str).replace({"None": None, "nan": None})


def options_for(definitions: list[dict[str, str]], frame: pd.DataFrame, selections: dict[str, list[str]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for definition in definitions:
        key = definition["key"]
        if key not in frame.columns:
            output.append({**definition, "options": [], "truncated": False})
            continue
        filtered = frame
        for other_key, values in selections.items():
            if other_key == key or other_key not in frame.columns or not values:
                continue
            filtered = filtered[filtered[other_key].isin(values)]
        values = sorted({str(value).strip() for value in filtered[key].dropna().tolist() if str(value).strip()}, key=str.casefold)
        output.append({**definition, "options": values[:3000], "truncated": len(values) > 3000})
    return output


# ── Auditoría, errores y respuestas ────────────────────────────────────────
def log_event(kind: str, detail: str, payload: str) -> None:
    if DEMO_MODE:
        return
    snowflake.log_event(kind, "Tejido Empresarial", detail, payload)


def error_consulta(mensaje: str) -> str:
    """Mensaje para el usuario con la causa real, sin secretos.

    La causa se incluye siempre: sin ella el aplicativo sólo dice «no se pudo» y
    quien administra el despliegue no tiene por dónde empezar. Los textos pasan
    por `redactar()`, que elimina llaves, frases y valores sensibles.
    """
    if DEMO_MODE:
        return f"{mensaje} Intenta nuevamente en unos segundos."
    causa = snowflake.ultimo_error_consulta or snowflake.ultimo_error
    if causa:
        return f"{mensaje} Causa: {causa}. Más detalle en la página /estado."
    return (
        f"{mensaje} Si vuelve a ocurrir, abra la página /estado para ver en qué paso falla "
        "la conexión con Snowflake, o revise los registros del servicio."
    )


def require_connection() -> None:
    if not DEMO_MODE and not snowflake.configured:
        raise HTTPException(status_code=503, detail="La conexión de datos aún no está configurada en este entorno.")


#: Tamaño de cada trozo de una descarga. Sin él, `StreamingResponse` recorre un
#: BytesIO «por líneas», que en un .xlsx binario son miles de trozos diminutos.
TROZO_DESCARGA = 64 * 1024


def _trozos(contenido: Any) -> Iterator[bytes]:
    """Trozos de tamaño fijo, venga el archivo como bytes, como buffer o como iterable."""
    if isinstance(contenido, (bytes, bytearray)):
        datos = bytes(contenido)
        for inicio in range(0, len(datos), TROZO_DESCARGA):
            yield datos[inicio : inicio + TROZO_DESCARGA]
        return
    if hasattr(contenido, "read"):
        while True:
            trozo = contenido.read(TROZO_DESCARGA)
            if not trozo:
                return
            yield trozo
        return
    yield from contenido


def respuesta_archivo(contenido: Any, nombre: str, tipo: str) -> StreamingResponse:
    """Descarga con nombre legible: `Content-Disposition` RFC 5987 y una cabecera simple para el navegador."""
    codificado = quote(nombre)
    return StreamingResponse(
        _trozos(contenido),
        media_type=tipo,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{codificado}",
            "X-Export-Filename": codificado,
            "Cache-Control": "no-store",
        },
    )
