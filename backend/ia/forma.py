"""
Forma del resultado del asistente: nombres legibles, columnas de contacto y
detección de listados de empresas.

Vive aparte de `graficos.py` porque son decisiones distintas: aquí se decide
**cómo se presenta y qué se puede descargar**; allá, si el resultado se presta a
una gráfica. Las tres reglas se prueban sin navegador ni Snowflake.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any

from backend.config import CONTACT_COLUMNS, QUERY_COLUMNS

#: Nombres técnicos de las columnas de contacto (EMAIL, TELEFONO, …), derivados
#: del mismo catálogo que gobierna la descarga estándar.
_CONTACTO_TECNICO = frozenset(
    tecnico for tecnico, etiqueta_ in QUERY_COLUMNS.items() if etiqueta_ in CONTACT_COLUMNS
)
#: Fragmentos que delatan contacto aunque el modelo invente un alias
#: («CORREO_EMPRESA», «TELEFONO_CONTACTO», «Dirección comercial»).
_SENALES_CONTACTO = ("EMAIL", "CORREO", "TELEFONO", "CELULAR", "DIRECCION", "REPRESENTANTE")
_NIT = re.compile(r"^\d{2,12}$")
_ALIAS_TECNICO = re.compile(r"^[A-Z][A-Z0-9_]*$")
#: Siglas que conservan mayúsculas al volver legible un alias («Exportaciones 2025 USD»).
_SIGLAS = frozenset({"USD", "COP", "FOB", "NIT", "CIIU", "PDET", "ZOMAC", "HUB", "NME", "PCT", "DANE", "ID"})
#: Proporción mínima de valores con forma de NIT para tratar la columna como tal.
_PROPORCION_NIT = 0.8


def normalizar(nombre: str) -> str:
    """«Correo electrónico» → «CORREO_ELECTRONICO»: sin tildes, en mayúsculas, con guiones bajos."""
    ascii_ = unicodedata.normalize("NFKD", str(nombre)).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Za-z0-9]+", "_", ascii_).strip("_").upper()


def es_columna_contacto(nombre: str) -> bool:
    """¿La columna trae datos de contacto o de representación legal?"""
    clave = normalizar(nombre)
    if clave in _CONTACTO_TECNICO or nombre in CONTACT_COLUMNS:
        return True
    return any(senal in clave for senal in _SENALES_CONTACTO)


def etiqueta(nombre: str) -> str:
    """Etiqueta institucional si la columna es conocida; si no, el alias del modelo, legible."""
    conocida = QUERY_COLUMNS.get(nombre) or QUERY_COLUMNS.get(nombre.upper())
    if conocida:
        return conocida
    if _ALIAS_TECNICO.match(nombre) and len(nombre) > 1:
        palabras = nombre.replace("_", " ").capitalize().split(" ")
        return " ".join(p.upper() if p.upper() in _SIGLAS else p for p in palabras)
    return nombre


def columnas_legibles(columnas: list[str]) -> list[str]:
    """Etiquetas únicas: si dos alias caen en la misma etiqueta, la segunda se numera."""
    salida: list[str] = []
    vistas: dict[str, int] = {}
    for columna in columnas:
        texto = etiqueta(columna)
        repeticiones = vistas.get(texto, 0)
        vistas[texto] = repeticiones + 1
        salida.append(texto if repeticiones == 0 else f"{texto} ({repeticiones + 1})")
    return salida


def _como_nit(valor: Any) -> str | None:
    if valor is None or isinstance(valor, bool):
        return None
    if isinstance(valor, float):
        if not valor.is_integer():
            return None
        valor = int(valor)
    texto = str(valor).strip()
    return texto if _NIT.match(texto) else None


def nits_del_resultado(columnas: list[str], filas: list[list[Any]]) -> list[str]:
    """NIT distintos, en orden de aparición, si el resultado tiene una columna NIT.

    Se exige que al menos el 80 % de los valores no nulos parezcan NIT: así una
    columna llamada NIT que en realidad trae conteos no convierte un agregado en
    un «listado de empresas».
    """
    indice = next((i for i, columna in enumerate(columnas) if normalizar(columna) == "NIT"), None)
    if indice is None:
        return []
    vistos: list[str] = []
    conjunto: set[str] = set()
    no_nulos = 0
    validos = 0
    for fila in filas:
        if indice >= len(fila) or fila[indice] is None:
            continue
        no_nulos += 1
        nit = _como_nit(fila[indice])
        if nit is None:
            continue
        validos += 1
        if nit not in conjunto:
            conjunto.add(nit)
            vistos.append(nit)
    if not no_nulos or validos < _PROPORCION_NIT * no_nulos:
        return []
    return vistos
