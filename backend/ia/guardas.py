"""
Guardas del asistente: qué SQL se deja ejecutar y qué cifras se dejan afirmar.

Son las dos barreras que permiten mostrar respuestas de un modelo sin que el
usuario tenga que confiar en él:

1. `validar_sql` — aunque la consulta venga de Cortex Analyst, aquí se exige que
   sea **una sola sentencia de lectura**, que todo origen de datos apunte a los
   esquemas permitidos y que tenga un tope de filas. Cualquier otra cosa se
   rechaza antes de tocar la base.
2. `verificar_cifras` — ninguna cifra del texto redactado puede ser ajena al
   resultado de la consulta. Si aparece una, la respuesta se reemplaza por un
   resumen determinista construido con los datos reales.

La validación trabaja sobre **fichas** (tokens) producidas por un lector que
conoce las tres formas de comentario de Snowflake (`--`, `//`, `/* */`), las
cadenas con comilla simple y las cadenas delimitadas por `$$`. Ese detalle es la
guarda de fondo: si el lector y Snowflake no coinciden en dónde empieza y
termina un literal, un comentario con una comilla dentro puede esconder un
`UNION` a otra tabla, y lo validado deja de ser lo ejecutado. Por eso toda
construcción sin cerrar se rechaza en vez de interpretarse.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

#: Palabras que no tienen lugar en una consulta de lectura. Se comparan ficha a
#: ficha, por lo que ``LISTAGG`` o ``DESC`` (de ORDER BY) no se confunden.
_PROHIBIDAS = frozenset(
    {
        "INSERT", "UPDATE", "DELETE", "MERGE", "DROP", "ALTER", "CREATE", "GRANT", "REVOKE",
        "TRUNCATE", "CALL", "COPY", "PUT", "GET", "UNDROP", "EXECUTE", "USE", "SET", "UNSET",
        "COMMENT", "DESCRIBE", "SHOW", "LIST", "REMOVE", "BEGIN", "COMMIT", "ROLLBACK",
        "RESULT_SCAN", "GET_DDL", "IDENTIFIER", "INFORMATION_SCHEMA", "ACCOUNT_USAGE",
    }
)
#: Funciones de tabla que sí puede usar la consulta como origen de datos. Todo
#: lo demás (``IDENTIFIER('…')``, ``TABLE(…)``, ``RESULT_SCAN``) se rechaza.
_ORIGENES_FUNCION = frozenset({"SEMANTIC_VIEW", "LATERAL", "FLATTEN"})
#: Palabras que cierran la cláusula FROM. `ON`, `USING` y las variantes de JOIN
#: NO están: tras ellas puede seguir una coma que introduce otra tabla.
_FIN_DE_CLAUSULA = frozenset(
    {
        "WHERE", "GROUP", "ORDER", "LIMIT", "HAVING", "QUALIFY", "UNION", "EXCEPT", "INTERSECT",
        "MINUS", "WINDOW", "SELECT", "FETCH", "OFFSET", "PIVOT", "UNPIVOT", "SAMPLE",
        "TABLESAMPLE", "CONNECT", "START", "MATCH_RECOGNIZE", "WITH",
    }
)
#: Fichas del lector, en orden de prioridad. Los comentarios y las cadenas se
#: reconocen ANTES que cualquier otra cosa.
_PATRON = re.compile(
    r"(?P<comentario_linea>(?:--|//)[^\n]*)"
    r"|(?P<comentario_bloque>/\*[\s\S]*?\*/)"
    r"|(?P<cadena_dolar>\$\$[\s\S]*?\$\$)"
    r"|(?P<cadena>'(?:[^'\\]|\\.|'')*')"
    r"|(?P<entrecomillado>\"(?:[^\"]|\"\")*\")"
    r"|(?P<nombre>[A-Za-z_][A-Za-z0-9_$]*)"
    r"|(?P<numero>\d+(?:\.\d+)?)"
    r"|(?P<otro>\S)"
)
#: Fichas que delatan una cadena o un comentario sin cerrar: el lector no pudo
#: emparejarlos y Snowflake los leería de otra manera.
_SIN_CERRAR = {"'", '"'}


@dataclass
class SqlValidada:
    """SQL lista para ejecutar, o el motivo por el que no se ejecutará."""

    ok: bool
    sql: str = ""
    motivo: str = ""


@dataclass
class Ficha:
    """Una ficha del lector, con su posición en la SQL original."""

    texto: str
    inicio: int
    fin: int

    @property
    def arriba(self) -> str:
        return self.texto.upper()


class ErrorDeLectura(ValueError):
    """La SQL tiene una cadena o un comentario sin cerrar."""


def leer_fichas(sql: str) -> list[Ficha]:
    """Fichas significativas de la SQL: sin comentarios y con las cadenas enteras.

    Raises:
        ErrorDeLectura: si queda una cadena o un comentario sin cerrar, caso en
            el que el lector y Snowflake interpretarían cosas distintas.
    """
    fichas: list[Ficha] = []
    for coincidencia in _PATRON.finditer(sql):
        tipo = coincidencia.lastgroup
        texto = coincidencia.group()
        if tipo in {"comentario_linea", "comentario_bloque"}:
            continue
        if tipo == "otro":
            if texto in _SIN_CERRAR:
                raise ErrorDeLectura("La consulta tiene una cadena de texto sin cerrar.")
            if texto == "$" and fichas and fichas[-1].texto == "$":
                raise ErrorDeLectura("La consulta tiene una cadena $$ sin cerrar.")
            if texto == "*" and fichas and fichas[-1].texto == "/" and fichas[-1].fin == coincidencia.start():
                raise ErrorDeLectura("La consulta tiene un comentario /* sin cerrar.")
        fichas.append(Ficha(texto, coincidencia.start(), coincidencia.end()))
    return fichas


def _es_identificador(ficha: str) -> bool:
    return ficha.startswith('"') or bool(re.match(r"[A-Za-z_]", ficha))


def _sin_comillas(parte: str) -> str:
    return parte[1:-1].replace('""', '"').upper() if parte.startswith('"') else parte.upper()


def _base_por_defecto(esquemas: frozenset[str]) -> str | None:
    """Si todos los esquemas permitidos viven en una base, un nombre de dos partes se resuelve en ella."""
    bases = {esquema.split(".")[0] for esquema in esquemas if "." in esquema}
    return next(iter(bases)) if len(bases) == 1 else None


def _ctes(textos: list[str]) -> set[str]:
    """Nombres declarados como CTE (``nombre AS (``, con o sin lista de columnas).

    Se calcula sobre fichas y no sobre el texto crudo: un literal que contenga
    «WITH X AS (» no puede dar de alta una tabla.
    """
    nombres: set[str] = set()
    for indice, texto in enumerate(textos):
        if not _es_identificador(texto):
            continue
        siguiente = indice + 1
        if siguiente < len(textos) and textos[siguiente] == "(":  # lista de columnas
            nivel = 0
            while siguiente < len(textos):
                if textos[siguiente] == "(":
                    nivel += 1
                elif textos[siguiente] == ")":
                    nivel -= 1
                    if nivel == 0:
                        siguiente += 1
                        break
                siguiente += 1
        if siguiente + 1 < len(textos) and textos[siguiente].upper() == "AS" and textos[siguiente + 1] == "(":
            nombres.add(_sin_comillas(texto))
    return nombres


def _origenes(textos: list[str]) -> list[tuple[str, bool, bool]]:
    """Nombres usados como origen de datos: (nombre, es_función, dentro_de_vista_semántica).

    Recorre las fichas con una pila por nivel de paréntesis. Cada nivel guarda
    si se espera un nombre (tras FROM o JOIN) y si sigue abierta la cláusula
    FROM, donde una coma introduce otra tabla. Un paréntesis que sigue a FROM o
    JOIN hereda la espera de nombre, porque Snowflake admite agrupar joins
    entre paréntesis (``FROM t1 JOIN (t2 JOIN t3 ON …) ON …``).
    """
    origenes: list[tuple[str, bool, bool]] = []
    pila: list[list[bool]] = [[False, False]]  # [esperando_nombre, en_from]
    dentro_de_vista = [False]
    i = 0
    while i < len(textos):
        texto = textos[i]
        arriba = texto.upper()
        estado = pila[-1]
        if texto == "(":
            hereda = estado[0]
            estado[0] = False
            pila.append([hereda, hereda])
            dentro_de_vista.append(dentro_de_vista[-1])
            i += 1
            continue
        if texto == ")":
            if len(pila) > 1:
                pila.pop()
                dentro_de_vista.pop()
            i += 1
            continue
        if arriba in {"FROM", "JOIN"}:
            estado[0] = estado[1] = True
            i += 1
            continue
        if estado[0]:
            if arriba == "LATERAL":
                i += 1
                continue
            if _es_identificador(texto):
                partes = [texto]
                j = i + 1
                while j + 1 < len(textos) and textos[j] == "." and _es_identificador(textos[j + 1]):
                    partes.append(textos[j + 1])
                    j += 2
                es_funcion = j < len(textos) and textos[j] == "("
                origenes.append((".".join(partes), es_funcion, dentro_de_vista[-1]))
                estado[0] = False
                if es_funcion and _sin_comillas(partes[-1]) == "SEMANTIC_VIEW":
                    # El primer nombre dentro del paréntesis es la vista: se registra
                    # también, marcado, para aplicarle la regla de esquemas.
                    k = j + 1
                    if k < len(textos) and _es_identificador(textos[k]):
                        partes_vista = [textos[k]]
                        m = k + 1
                        while m + 1 < len(textos) and textos[m] == "." and _es_identificador(textos[m + 1]):
                            partes_vista.append(textos[m + 1])
                            m += 2
                        origenes.append((".".join(partes_vista), False, True))
                i = j
                continue
            estado[0] = False
            i += 1
            continue
        if estado[1]:
            if texto == ",":
                estado[0] = True
            elif arriba in _FIN_DE_CLAUSULA:
                estado[1] = False
        i += 1
    return origenes


def _acotar_limite(sql: str, fichas: list[Ficha], max_filas: int) -> str:
    """Impone el tope de filas sin envolver la consulta (para no perder el ORDER BY).

    Si hay un LIMIT, TOP o FETCH de nivel superior mayor que el tope, se reduce
    en su sitio; si no hay ninguno, se añade un LIMIT al final —en una línea
    nueva, para que un comentario de línea final no se lo trague—.
    """
    nivel = 0
    for indice, ficha in enumerate(fichas):
        if ficha.texto == "(":
            nivel += 1
        elif ficha.texto == ")":
            nivel -= 1
        elif nivel == 0 and ficha.arriba in {"LIMIT", "TOP", "FETCH"}:
            # FETCH FIRST|NEXT <n> ROWS ONLY: el número puede venir dos fichas después.
            numero = None
            for siguiente in fichas[indice + 1 : indice + 4]:
                if siguiente.texto.isdigit():
                    numero = siguiente
                    break
                if siguiente.arriba not in {"FIRST", "NEXT"}:
                    break
            if numero is None:
                # `FETCH FIRST ROW ONLY` (una fila) o `LIMIT ?`: ya está acotado o no es un tope legible.
                return sql if ficha.arriba == "FETCH" else f"{sql}\nLIMIT {int(max_filas)}"
            if int(numero.texto) > max_filas:
                return sql[: numero.inicio] + str(int(max_filas)) + sql[numero.fin :]
            return sql
    return f"{sql}\nLIMIT {int(max_filas)}"


def validar_sql(sql_cruda: str, esquemas_permitidos: frozenset[str], max_filas: int) -> SqlValidada:
    """Comprueba que la SQL sea un único SELECT de solo lectura, acotado y sobre los esquemas permitidos.

    Args:
        sql_cruda: Sentencia propuesta por Cortex Analyst.
        esquemas_permitidos: Conjunto ``{"BASE.ESQUEMA", …}`` en mayúsculas.
        max_filas: Tope que se impone con ``LIMIT`` si la consulta no trae uno menor.
    """
    sql = (sql_cruda or "").strip()
    if not sql:
        return SqlValidada(ok=False, motivo="La consulta llegó vacía.")
    try:
        fichas = leer_fichas(sql)
    except ErrorDeLectura as exc:
        return SqlValidada(ok=False, motivo=str(exc))
    # Un punto y coma final es sólo puntuación: se retira antes de validar.
    while fichas and fichas[-1].texto == ";":
        sql = sql[: fichas[-1].inicio].rstrip()
        fichas.pop()
    if not fichas:
        return SqlValidada(ok=False, motivo="La consulta llegó vacía.")
    textos = [ficha.texto for ficha in fichas]

    primera = next((texto.upper() for texto in textos if texto != "("), "")
    if primera not in {"SELECT", "WITH"}:
        return SqlValidada(ok=False, motivo="Sólo se permiten consultas de lectura (SELECT o WITH).")

    for indice, texto in enumerate(textos):
        if texto == ";":
            return SqlValidada(ok=False, motivo="Se rechazan varias sentencias en una sola consulta.")
        if texto == "@":
            return SqlValidada(ok=False, motivo="No se permiten stages como origen de datos (@…).")
        if texto == "$" and indice + 1 < len(textos) and _es_identificador(textos[indice + 1]):
            return SqlValidada(ok=False, motivo="No se permiten variables de sesión ($…).")
        if _es_identificador(texto) and not texto.startswith('"'):
            arriba = texto.upper()
            if arriba in _PROHIBIDAS:
                return SqlValidada(ok=False, motivo=f"Instrucción no permitida: {arriba}.")
            if arriba.startswith("SYSTEM$"):
                return SqlValidada(ok=False, motivo="No se permiten funciones de sistema (SYSTEM$…).")

    # Todo nombre de tres partes, esté donde esté, debe caer en un esquema permitido.
    for indice in range(len(textos) - 4):
        if (
            _es_identificador(textos[indice])
            and textos[indice + 1] == "."
            and _es_identificador(textos[indice + 2])
            and textos[indice + 3] == "."
            and _es_identificador(textos[indice + 4])
        ):
            par = f"{_sin_comillas(textos[indice])}.{_sin_comillas(textos[indice + 2])}"
            if par not in esquemas_permitidos:
                return SqlValidada(ok=False, motivo=f"La consulta apunta a un esquema no autorizado: {par}.")

    base = _base_por_defecto(esquemas_permitidos)
    ctes = _ctes(textos)
    for nombre, es_funcion, en_vista in _origenes(textos):
        partes = [_sin_comillas(parte) for parte in nombre.split(".")]
        if es_funcion:
            if partes[-1] not in _ORIGENES_FUNCION:
                return SqlValidada(ok=False, motivo=f"Origen de datos no permitido: {partes[-1]}(…).")
            continue
        if len(partes) == 3:
            par = f"{partes[0]}.{partes[1]}"
        elif len(partes) == 2:
            if base is None:
                return SqlValidada(ok=False, motivo=f"Nombre de dos partes no resoluble: {nombre}.")
            par = f"{base}.{partes[0]}"
        else:
            if partes[0] in ctes or en_vista:
                continue
            return SqlValidada(ok=False, motivo=f"Tabla sin calificar (base.esquema.tabla): {nombre}.")
        if par not in esquemas_permitidos:
            return SqlValidada(ok=False, motivo=f"La consulta apunta a un esquema no autorizado: {par}.")

    return SqlValidada(ok=True, sql=_acotar_limite(sql, fichas, max_filas))


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


def _es_numero(valor: Any) -> bool:
    return isinstance(valor, (int, float)) and not isinstance(valor, bool)


def _es_ano(token: str, magnitud: float) -> bool:
    """Un año en prosa se escribe sin separador de miles: «2024», nunca «2.024».

    La distinción importa: sin ella, una cifra inventada como «1.950 empresas»
    pasaría por año y no se detectaría.
    """
    return token.lstrip("-").isdigit() and 1900 <= magnitud <= 2100


def verificar_cifras(
    texto: str, filas: list[list[Any]], n_filas: int, pregunta: str = "", truncado: bool = False
) -> VerificacionCifras:
    """Comprueba que toda cifra del texto exista en el resultado o sea trivial.

    Se aceptan: los valores de cualquier celda (con redondeos y con escalas de
    miles/millones), el número de filas, las cifras que venían en la pregunta,
    los años, los enteros hasta 100 (ordinales del tipo «los 10 principales») y
    —sólo cuando el resultado está completo— la suma y el promedio de cada
    columna numérica. Si el resultado se recortó (``truncado``), un total sería
    parcial y engañoso, así que no se acepta. Cualquier otra cifra es huérfana.

    El signo no se tiene en cuenta: en la prosa, un guion suele ser un rango
    («2021-2025») o una raya, no un menos, y la tabla ya aporta cada valor con
    su valor absoluto.
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
                    permitidas.add(abs(numero))
    if filas and not truncado:
        for indice in range(max(len(fila) for fila in filas)):
            valores = [float(fila[indice]) for fila in filas if indice < len(fila) and _es_numero(fila[indice])]
            if valores:
                total = sum(valores)
                permitidas.add(abs(total))
                permitidas.add(abs(total / len(valores)))
    for token in _NUMERO.findall(pregunta):
        numero = _a_float(token)
        if numero is not None:
            permitidas.add(abs(numero))

    huerfanas: list[str] = []
    for token in _NUMERO.findall(texto):
        numero = _a_float(token)
        if numero is None:
            continue
        magnitud = abs(numero)
        if magnitud <= _ENTERO_TRIVIAL and magnitud.is_integer():
            continue
        if _es_ano(token, magnitud):
            continue
        if not any(_equivalentes(magnitud, abs(permitida)) for permitida in permitidas):
            huerfanas.append(token)
    return VerificacionCifras(ok=not huerfanas, huerfanas=huerfanas)
