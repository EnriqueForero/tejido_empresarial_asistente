"""
Guardas del asistente: qué SQL se deja ejecutar y qué cifras se dejan afirmar.

Son las dos barreras que permiten mostrar respuestas de un modelo sin que el
usuario tenga que confiar en él:

1. `validar_sql` — aunque la consulta venga de Cortex Analyst, aquí se exige que
   sea **una sola sentencia de lectura**, sobre los esquemas permitidos y con un
   tope de filas. Cualquier otra cosa se rechaza antes de tocar la base.
2. `verificar_cifras` — ninguna cifra del texto redactado puede ser ajena al
   resultado de la consulta. Si aparece una, la respuesta se reemplaza por un
   resumen determinista construido con los datos reales.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

_PROHIBIDAS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|MERGE|DROP|ALTER|CREATE|GRANT|REVOKE|TRUNCATE|CALL|"
    r"COPY|PUT|GET|UNDROP|EXECUTE|USE|SET|UNSET|COMMENT|DESCRIBE|SHOW)\b",
    re.IGNORECASE,
)
_LIMIT = re.compile(r"\bLIMIT\s+\d+", re.IGNORECASE)
_CALIFICADO = re.compile(r"\b([A-Z_][A-Z0-9_$]*)\s*\.\s*([A-Z_][A-Z0-9_$]*)\s*\.", re.IGNORECASE)
_COMENTARIO_LINEA = re.compile(r"--[^\n]*")
_COMENTARIO_BLOQUE = re.compile(r"/\*.*?\*/", re.DOTALL)


@dataclass
class SqlValidada:
    """SQL lista para ejecutar, o el motivo por el que no se ejecutará."""

    ok: bool
    sql: str = ""
    motivo: str = ""


def _limpiar(sql: str) -> str:
    sin_bloques = _COMENTARIO_BLOQUE.sub(" ", sql)
    sin_linea = _COMENTARIO_LINEA.sub(" ", sin_bloques)
    return sin_linea.strip().rstrip(";").strip()


def validar_sql(sql_cruda: str, esquemas_permitidos: frozenset[str], max_filas: int) -> SqlValidada:
    """Comprueba que la SQL sea un único SELECT de solo lectura y acotado.

    Args:
        sql_cruda: Sentencia propuesta por Cortex Analyst.
        esquemas_permitidos: Conjunto ``{"BASE.ESQUEMA", …}`` en mayúsculas.
        max_filas: Tope que se impone con ``LIMIT`` si la consulta no trae uno.
    """
    sql = _limpiar(sql_cruda)
    if not sql:
        return SqlValidada(ok=False, motivo="La consulta llegó vacía.")
    if ";" in sql:
        return SqlValidada(ok=False, motivo="Se rechazan varias sentencias en una sola consulta.")
    inicio = sql.lstrip("( \n\t").upper()
    if not (inicio.startswith("SELECT") or inicio.startswith("WITH")):
        return SqlValidada(ok=False, motivo="Sólo se permiten consultas de lectura (SELECT o WITH).")
    prohibida = _PROHIBIDAS.search(sql)
    if prohibida:
        return SqlValidada(ok=False, motivo=f"Instrucción no permitida: {prohibida.group(1).upper()}.")
    for base, esquema in _CALIFICADO.findall(sql):
        par = f"{base}.{esquema}".upper()
        if par not in esquemas_permitidos:
            return SqlValidada(ok=False, motivo=f"La consulta apunta a un esquema no autorizado: {par}.")
    if not _LIMIT.search(sql):
        sql = f"SELECT * FROM (\n{sql}\n) LIMIT {int(max_filas)}"
    return SqlValidada(ok=True, sql=sql)


# ── Verificación de cifras ────────────────────────────────────────────────

# El separador final de una frase («… y Caldas 45.912.») no forma parte del número.
_NUMERO = re.compile(r"-?\d(?:[\d.,]*\d)?")
_ENTERO_TRIVIAL = 100          # ordinales y porcentajes redondos citados en prosa
_TOLERANCIA_RELATIVA = 1e-6


def _a_float(token: str) -> float | None:
    """Interpreta «1.234.567,89», «1,234,567.89» o «2024» como número."""
    texto = token.strip()
    if not texto or texto in {"-", ".", ","}:
        return None
    if "." in texto and "," in texto:
        decimal = "," if texto.rfind(",") > texto.rfind(".") else "."
        miles = "." if decimal == "," else ","
        texto = texto.replace(miles, "").replace(decimal, ".")
    elif "," in texto:
        partes = texto.split(",")
        texto = texto.replace(",", "") if len(partes[-1]) == 3 and len(partes) > 1 else texto.replace(",", ".")
    elif texto.count(".") > 1 or (texto.count(".") == 1 and len(texto.split(".")[-1]) == 3 and len(texto) > 4):
        texto = texto.replace(".", "")
    try:
        return float(texto)
    except ValueError:
        return None


def _equivalentes(citado: float, real: float) -> bool:
    if citado == real:
        return True
    escala = max(abs(citado), abs(real), 1.0)
    if abs(citado - real) <= _TOLERANCIA_RELATIVA * escala:
        return True
    # La redacción puede redondear lo que la base trae con decimales.
    if any(abs(round(real, d) - citado) <= 10 ** (-d) * 0.51 for d in (0, 1, 2)):
        return True
    # …o expresar en millones/miles de millones lo que la base trae en unidades.
    return any(
        abs(round(real / factor, d) - citado) <= 10 ** (-d) * 0.51
        for factor in (1_000, 1_000_000, 1_000_000_000)
        for d in (0, 1, 2)
    )


@dataclass
class VerificacionCifras:
    """Veredicto con las cifras del texto que no tienen respaldo en los datos."""

    ok: bool
    huerfanas: list[str] = field(default_factory=list)


def verificar_cifras(
    texto: str, filas: list[list[Any]], n_filas: int, pregunta: str = ""
) -> VerificacionCifras:
    """Comprueba que toda cifra del texto exista en el resultado o sea trivial.

    Se aceptan: los valores de cualquier celda (con redondeos y con escalas de
    miles/millones), el número de filas, las cifras que venían en la pregunta,
    los años y los enteros hasta 100 (ordinales del tipo «los 10 principales»).
    Cualquier otra cifra se considera huérfana.
    """
    permitidas: set[float] = {float(n_filas)}
    for fila in filas:
        for valor in fila:
            if isinstance(valor, bool):
                continue
            if isinstance(valor, (int, float)):
                permitidas.add(float(valor))
                permitidas.add(abs(float(valor)))
            elif isinstance(valor, str):
                numero = _a_float(valor)
                if numero is not None:
                    permitidas.add(numero)
    for token in _NUMERO.findall(pregunta):
        numero = _a_float(token)
        if numero is not None:
            permitidas.add(numero)

    huerfanas: list[str] = []
    for token in _NUMERO.findall(texto):
        numero = _a_float(token)
        if numero is None:
            continue
        if abs(numero) <= _ENTERO_TRIVIAL and float(numero).is_integer():
            continue
        if 1900 <= numero <= 2100 and float(numero).is_integer():
            continue  # años citados en prosa
        if not any(_equivalentes(numero, permitida) for permitida in permitidas):
            huerfanas.append(token)
    return VerificacionCifras(ok=not huerfanas, huerfanas=huerfanas)
