from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from backend.config import FILTERS_BY_KEY


SearchMode = Literal["filters", "business_name", "nit", "batch_nits"]

MODE_LABELS: dict[str, str] = {
    "filters": "Segmentación por filtros",
    "business_name": "Búsqueda por razón social",
    "nit": "Búsqueda por NIT",
    "batch_nits": "Búsqueda masiva por NIT",
}


def _clean_filters(selections: dict[str, list[str]]) -> dict[str, list[str]]:
    if len(selections) > len(FILTERS_BY_KEY):
        raise ValueError("Demasiados filtros.")
    unknown = sorted(set(selections) - set(FILTERS_BY_KEY))
    if unknown:
        raise ValueError(f"Filtros no permitidos: {', '.join(unknown)}.")
    cleaned: dict[str, list[str]] = {}
    for key, values in selections.items():
        if len(values) > 250:
            raise ValueError(f"Demasiados valores para {key}.")
        unique: list[str] = []
        seen: set[str] = set()
        for value in values:
            item = str(value).strip()[:300]
            if item and item not in seen:
                seen.add(item)
                unique.append(item)
        if unique:
            cleaned[key] = unique
    return cleaned


def clean_nit(value: object) -> str:
    return "".join(character for character in str(value) if character.isdigit())


class FilterOptionsRequest(BaseModel):
    selections: dict[str, list[str]] = Field(default_factory=dict)

    @field_validator("selections")
    @classmethod
    def limit_selections(cls, selections: dict[str, list[str]]) -> dict[str, list[str]]:
        return _clean_filters(selections)


class SearchRequest(BaseModel):
    mode: SearchMode = "filters"
    filters: dict[str, list[str]] = Field(default_factory=dict)
    term: str = ""
    nits: list[str] = Field(default_factory=list)
    page: int = Field(default=1, ge=1, le=400)
    page_size: int = Field(default=25, ge=10, le=100)

    @field_validator("filters")
    @classmethod
    def clean_filters(cls, selections: dict[str, list[str]]) -> dict[str, list[str]]:
        return _clean_filters(selections)

    @field_validator("term")
    @classmethod
    def clean_term(cls, value: str) -> str:
        return value.strip()[:180]

    @field_validator("nits")
    @classmethod
    def clean_nits(cls, values: list[str]) -> list[str]:
        unique: list[str] = []
        seen: set[str] = set()
        for value in values:
            nit = clean_nit(value)
            if 2 <= len(nit) <= 12 and nit not in seen:
                seen.add(nit)
                unique.append(nit)
            if len(unique) >= 5000:
                break
        return unique

    @model_validator(mode="after")
    def validate_mode_payload(self) -> "SearchRequest":
        if self.mode in {"business_name", "nit"} and not self.term:
            raise ValueError("Escribe un criterio de búsqueda.")
        if self.mode == "business_name" and len(self.term) < 2:
            raise ValueError("Escribe al menos dos caracteres de la razón social.")
        if self.mode == "nit" and not any(character.isdigit() for character in self.term):
            raise ValueError("El NIT debe contener números.")
        if self.mode == "batch_nits" and not self.nits:
            raise ValueError("Carga al menos un NIT válido.")
        return self

    def summary(self) -> str:
        """Descripción corta de la consulta, para trazabilidad y nombres de archivo."""
        if self.mode == "business_name":
            return f"razón social contiene «{self.term}»"
        if self.mode == "nit":
            return f"NIT contiene «{clean_nit(self.term)}»"
        if self.mode == "batch_nits":
            return f"lote de {len(self.nits)} NIT"
        active = sum(len(values) for values in self.filters.values())
        return f"{active} criterio(s) de filtro" if active else "toda la base empresarial"


_ID_CONSULTA = re.compile(r"^[0-9a-f]{12}$")
_ID_SESION = re.compile(r"^[A-Za-z0-9_-]{0,64}$")
_PAPELES = {"user", "analyst"}
_BLOQUES = {"text", "sql", "suggestions"}


def _validar_turno(turno: dict[str, Any]) -> dict[str, Any]:
    """Un turno del historial en el formato de Cortex Analyst, acotado en forma y tamaño."""
    if not isinstance(turno, dict) or turno.get("role") not in _PAPELES:
        raise ValueError("Cada turno del historial debe tener role «user» o «analyst».")
    contenido = turno.get("content")
    if not isinstance(contenido, list) or not 1 <= len(contenido) <= 6:
        raise ValueError("Cada turno del historial debe traer entre 1 y 6 bloques de contenido.")
    limpio: list[dict[str, Any]] = []
    for bloque in contenido:
        if not isinstance(bloque, dict) or bloque.get("type") not in _BLOQUES:
            raise ValueError("Bloque de historial no reconocido.")
        tipo = bloque["type"]
        if tipo == "text":
            texto = str(bloque.get("text", ""))[:2000]
            limpio.append({"type": "text", "text": texto})
        elif tipo == "sql":
            sentencia = str(bloque.get("statement", ""))[:20000]
            limpio.append({"type": "sql", "statement": sentencia})
        else:
            sugerencias = [str(s)[:300] for s in (bloque.get("suggestions") or [])][:10]
            limpio.append({"type": "suggestions", "suggestions": sugerencias})
    return {"role": turno["role"], "content": limpio}


class PreguntaIA(BaseModel):
    """Pregunta en lenguaje natural para el asistente de análisis."""

    pregunta: str = Field(default="", max_length=2000)
    #: Identificadores de las respuestas anteriores del hilo: el servidor
    #: reconstruye con ellos el historial real que devolvió Cortex Analyst.
    consulta_ids: list[str] = Field(default_factory=list, max_length=6)
    #: Historial en el formato de Analyst, como respaldo si el servidor ya no
    #: conserva esas respuestas (pestaña antigua o resultado vencido).
    historial: list[dict[str, Any]] = Field(default_factory=list, max_length=12)
    #: Identificador de la pestaña, sólo para la telemetría.
    sesion_id: str = Field(default="", max_length=64)

    @field_validator("pregunta")
    @classmethod
    def limpiar_pregunta(cls, valor: str) -> str:
        return valor.strip()

    @field_validator("consulta_ids")
    @classmethod
    def validar_ids(cls, valores: list[str]) -> list[str]:
        for valor in valores:
            if not _ID_CONSULTA.match(str(valor)):
                raise ValueError("Identificador de consulta no válido.")
        return [str(valor) for valor in valores]

    @field_validator("historial")
    @classmethod
    def validar_historial(cls, turnos: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [_validar_turno(turno) for turno in turnos]

    @field_validator("sesion_id")
    @classmethod
    def validar_sesion(cls, valor: str) -> str:
        return valor if _ID_SESION.match(valor) else ""


class DescargaIA(BaseModel):
    """Descarga de un resultado que el servidor ya tiene guardado."""

    consulta_id: str = Field(pattern=r"^[0-9a-f]{12}$")
    sesion_id: str = Field(default="", max_length=64)

    @field_validator("sesion_id")
    @classmethod
    def validar_sesion(cls, valor: str) -> str:
        return valor if _ID_SESION.match(valor) else ""
