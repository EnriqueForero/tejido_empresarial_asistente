"""
Elección de la gráfica a partir de la forma del resultado.

El servidor decide **qué** representar y el navegador sólo dibuja: así la regla
queda en un solo sitio, se puede probar sin navegador y la gráfica nunca
contradice a la tabla.

Criterios (en este orden):

- una sola fila y un solo número → **indicador**, no una gráfica de una barra;
- una columna de texto y una numérica → **barras horizontales de un solo tono**
  (la longitud ya codifica la magnitud; teñirlas por valor sería repetirlo);
- una de texto y varias numéricas → **barras agrupadas**, un color por medida;
- dos de texto y una numérica → **barras apiladas** (por ejemplo departamento ×
  tamaño), con la segunda dimensión como series;
- columnas que son años o periodos → **líneas**;
- cualquier otra forma → sin gráfica; la tabla es la respuesta.

La tabla siempre acompaña a la gráfica: es lo que permite leer los valores exactos
y es el respaldo accesible de los colores.
"""
from __future__ import annotations

import re
from typing import Any

#: Paleta categórica validada (contraste y daltonismo) en orden fijo. El orden es
#: el mecanismo de seguridad: no se reordena ni se generan tonos nuevos.
PALETA_CATEGORICA = [
    "#2a78d6",  # azul
    "#eb6834",  # naranja
    "#1baf7a",  # aguamarina
    "#eda100",  # amarillo
    "#e87ba4",  # magenta
    "#008300",  # verde
    "#4a3aa7",  # violeta
    "#e34948",  # rojo
]
#: Tono único para magnitudes de una sola medida.
TONO_UNICO = "#2a78d6"

MAX_CATEGORIAS = 20
MAX_SERIES = 6
_OTROS = "Otros"

# «EXPO_2021» no tiene frontera de palabra antes del año: el guion bajo también
# cuenta como carácter de palabra. Por eso se delimita con dígitos, no con \b.
_ANIO = re.compile(r"(?<!\d)(19|20)\d{2}(?!\d)")
_PERIODO = re.compile(r"(ene|feb|mar|abr|may|jun|jul|ago|sep|oct|nov|dic)[a-z_]*[ _-]*(19|20)\d{2}", re.IGNORECASE)


#: Palabras con las que el usuario pide ver una gráfica. La tabla es la respuesta
#: por defecto; la gráfica se abre sola sólo si la pregunta la nombra.
_PIDE_GRAFICA = re.compile(
    r"\b(gr[aá]f[ií]c(?:[ao]s?|[aá](?:r|me|lo|la))|visualiza(?:r|ci[oó]n|me)?|"
    r"diagrama|barras|l[ií]neas|evoluci[oó]n|tendencia|serie(?:s)?\s+(?:de\s+)?tiempo|comparativ[ao])\b",
    re.IGNORECASE,
)


def pide_grafica(pregunta: str) -> bool:
    """¿La pregunta pide de forma explícita una gráfica?"""
    return bool(_PIDE_GRAFICA.search(pregunta or ""))


def _es_numero(valor: Any) -> bool:
    return isinstance(valor, (int, float)) and not isinstance(valor, bool)


def _columna_numerica(filas: list[list[Any]], indice: int) -> bool:
    """Una columna es numérica si todos sus valores no nulos lo son."""
    vistos = 0
    for fila in filas:
        if indice >= len(fila):
            return False
        valor = fila[indice]
        if valor is None:
            continue
        if not _es_numero(valor):
            return False
        vistos += 1
    return vistos > 0


def _es_periodo(nombre: str) -> bool:
    return bool(_ANIO.search(nombre) or _PERIODO.search(nombre))


def _numero(valor: Any) -> float:
    return float(valor) if _es_numero(valor) else 0.0


def _recortar(categorias: list[str], valores: list[float], tope: int) -> tuple[list[str], list[float]]:
    """Deja las primeras `tope` categorías y agrupa el resto en «Otros»."""
    if len(categorias) <= tope:
        return categorias, valores
    resto = sum(valores[tope - 1 :])
    return categorias[: tope - 1] + [_OTROS], valores[: tope - 1] + [resto]


def _formato(nombre: str) -> str:
    """Cómo se escriben los valores del eje: moneda, porcentaje o entero."""
    texto = nombre.lower()
    if "%" in texto or "porcentaje" in texto or texto.startswith("pct"):
        return "porcentaje"
    if "usd" in texto or "fob" in texto or "expo" in texto:
        return "usd"
    if "cop" in texto or "ingreso" in texto or "activo" in texto or "utilidad" in texto:
        return "cop"
    return "entero"


def sugerir(columnas: list[str], filas: list[list[Any]]) -> dict[str, Any] | None:
    """Devuelve la especificación de la gráfica, o ``None`` si no corresponde.

    Returns:
        ``{"tipo", "titulo", "categorias", "series": [{"nombre","color","valores"}],
        "formato", "eje", "nota"}`` o ``None``.
    """
    if not columnas or not filas:
        return None

    indices_num = [i for i, _ in enumerate(columnas) if _columna_numerica(filas, i)]
    indices_txt = [i for i, _ in enumerate(columnas) if i not in indices_num]

    # Un único número: se lee mejor como cifra destacada que como una barra sola.
    if len(filas) == 1 and len(indices_num) == 1 and not indices_txt:
        indice = indices_num[0]
        return {
            "tipo": "indicador",
            "titulo": columnas[indice],
            "categorias": [columnas[indice]],
            "series": [{"nombre": columnas[indice], "color": TONO_UNICO, "valores": [_numero(filas[0][indice])]}],
            "formato": _formato(columnas[indice]),
            "eje": "",
            "nota": "",
        }

    # Una fila y varias columnas de periodo: la evolución de una misma medida.
    periodos = [i for i in indices_num if _es_periodo(columnas[i])]
    if len(filas) == 1 and len(periodos) >= 3:
        return {
            "tipo": "lineas",
            "titulo": "Evolución",
            "categorias": [columnas[i] for i in periodos],
            "series": [
                {
                    "nombre": "Valor",
                    "color": TONO_UNICO,
                    "valores": [_numero(filas[0][i]) for i in periodos],
                }
            ],
            "formato": _formato(columnas[periodos[0]]),
            "eje": "",
            "nota": "",
        }

    if not indices_txt or not indices_num:
        return None

    eje = indices_txt[0]
    categorias_crudas = [str(fila[eje]) if fila[eje] is not None else "Sin dato" for fila in filas]

    # Dos dimensiones de texto y una medida: barras apiladas (p. ej. departamento × tamaño).
    if len(indices_txt) >= 2 and len(indices_num) == 1:
        espec = _apiladas(columnas, filas, eje, indices_txt[1], indices_num[0])
        if espec is not None:
            return espec

    # Una dimensión y varias medidas: barras agrupadas, un color por medida.
    if len(indices_num) >= 2:
        medidas = [i for i in indices_num if not _es_periodo(columnas[i])] or indices_num
        medidas = medidas[:MAX_SERIES]
        if len(medidas) >= 2:
            categorias, _ = _recortar(categorias_crudas, [0.0] * len(categorias_crudas), MAX_CATEGORIAS)
            limite = len(categorias) - (1 if len(categorias_crudas) > MAX_CATEGORIAS else 0)
            series = []
            for orden, indice in enumerate(medidas):
                valores = [_numero(fila[indice]) for fila in filas]
                recortados = valores[:limite]
                if len(categorias_crudas) > MAX_CATEGORIAS:
                    recortados = recortados + [sum(valores[limite:])]
                series.append(
                    {
                        "nombre": columnas[indice],
                        "color": PALETA_CATEGORICA[orden % len(PALETA_CATEGORICA)],
                        "valores": recortados,
                    }
                )
            tipo = "lineas" if all(_es_periodo(columnas[i]) for i in medidas) else "agrupadas"
            return {
                "tipo": tipo,
                "titulo": "Comparación por " + columnas[eje].lower(),
                "categorias": categorias,
                "series": series,
                "formato": _formato(columnas[medidas[0]]),
                "eje": columnas[eje],
                "nota": _nota_recorte(len(categorias_crudas), MAX_CATEGORIAS),
            }

    # Una dimensión y una medida: barras de un solo tono.
    medida = indices_num[0]
    valores = [_numero(fila[medida]) for fila in filas]
    categorias, valores = _recortar(categorias_crudas, valores, MAX_CATEGORIAS)
    return {
        "tipo": "barras",
        "titulo": f"{columnas[medida]} por {columnas[eje].lower()}",
        "categorias": categorias,
        "series": [{"nombre": columnas[medida], "color": TONO_UNICO, "valores": valores}],
        "formato": _formato(columnas[medida]),
        "eje": columnas[eje],
        "nota": _nota_recorte(len(categorias_crudas), MAX_CATEGORIAS),
    }


def _apiladas(
    columnas: list[str], filas: list[list[Any]], eje: int, serie: int, medida: int
) -> dict[str, Any] | None:
    """Cruce de dos dimensiones: categorías en el eje y la segunda como series."""
    categorias: list[str] = []
    nombres_serie: list[str] = []
    acumulado: dict[tuple[str, str], float] = {}
    for fila in filas:
        categoria = str(fila[eje]) if fila[eje] is not None else "Sin dato"
        nombre = str(fila[serie]) if fila[serie] is not None else "Sin dato"
        if categoria not in categorias:
            categorias.append(categoria)
        if nombre not in nombres_serie:
            nombres_serie.append(nombre)
        clave = (categoria, nombre)
        acumulado[clave] = acumulado.get(clave, 0.0) + _numero(fila[medida])

    if len(nombres_serie) < 2 or len(nombres_serie) > MAX_SERIES or len(categorias) < 2:
        return None

    totales = {c: sum(acumulado.get((c, n), 0.0) for n in nombres_serie) for c in categorias}
    categorias.sort(key=lambda c: totales[c], reverse=True)
    recortadas = categorias[:MAX_CATEGORIAS]

    series = [
        {
            "nombre": nombre,
            "color": PALETA_CATEGORICA[orden % len(PALETA_CATEGORICA)],
            "valores": [acumulado.get((categoria, nombre), 0.0) for categoria in recortadas],
        }
        for orden, nombre in enumerate(nombres_serie)
    ]
    return {
        "tipo": "apiladas",
        "titulo": f"{columnas[medida]} por {columnas[eje].lower()} y {columnas[serie].lower()}",
        "categorias": recortadas,
        "series": series,
        "formato": _formato(columnas[medida]),
        "eje": columnas[eje],
        "nota": _nota_recorte(len(categorias), MAX_CATEGORIAS),
    }


def _nota_recorte(total: int, tope: int) -> str:
    if total <= tope:
        return ""
    return f"La gráfica muestra las {tope - 1} categorías mayores; el resto se agrupa en «{_OTROS}». La tabla trae las {total}."
