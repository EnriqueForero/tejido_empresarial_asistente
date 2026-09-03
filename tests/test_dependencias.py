"""
Las dos listas de dependencias no pueden desviarse.

El aplicativo declara sus dependencias de producción en `requirements-api.txt`.
El build de validación del notebook —que corre en Google Colab, donde el
conector de Snowflake no siempre se instala— usa `requirements-test.txt`.

Tener dos listas ya causó tres fallos de publicación: primero faltó
`cryptography`, después `pyarrow` y después `python-pptx`; en los tres casos el
error apareció en Colab, lejos de donde estaba la causa. Esta prueba lo detecta
aquí, al ejecutar el conjunto, y no allá.
"""
from __future__ import annotations

import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]

#: Dependencias de producción que a propósito NO se instalan para las pruebas.
#: Cada una lleva el motivo: si alguien quita una de aquí, la prueba lo obliga a
#: declararla en requirements-test.txt.
SOLO_PRODUCCION = {
    # El conector no siempre se instala en el Python de Colab; el backend lo
    # importa de forma tolerante y las pruebas corren en modo demostración.
    "snowflake-snowpark-python": "el conector no se instala en el entorno de pruebas",
}

_LINEA = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)\s*(\[[^\]]*\])?\s*(==|>=|<=|~=|!=|<|>)?")


def _paquetes(nombre_archivo: str) -> dict[str, str]:
    """Nombre normalizado → versión declarada, de un archivo de requisitos."""
    paquetes: dict[str, str] = {}
    for linea in (RAIZ / nombre_archivo).read_text(encoding="utf-8").splitlines():
        limpia = linea.split("#", 1)[0].strip()
        if not limpia or limpia.startswith("-"):
            continue
        coincidencia = _LINEA.match(limpia)
        if not coincidencia:
            continue
        nombre = coincidencia.group(1).lower().replace("_", "-")
        version = limpia[coincidencia.end(1) :]
        paquetes[nombre] = version.strip()
    return paquetes


def test_toda_dependencia_de_produccion_esta_en_la_lista_de_pruebas() -> None:
    produccion = _paquetes("requirements-api.txt")
    pruebas = _paquetes("requirements-test.txt")

    faltantes = sorted(set(produccion) - set(pruebas) - set(SOLO_PRODUCCION))
    assert not faltantes, (
        "Estas dependencias de producción no están en requirements-test.txt, así que el build de "
        f"validación del notebook fallará al ejecutar las pruebas: {faltantes}. Agréguelas allí con "
        "la misma versión, o justifíquelas en SOLO_PRODUCCION."
    )


def test_las_versiones_compartidas_coinciden() -> None:
    produccion = _paquetes("requirements-api.txt")
    pruebas = _paquetes("requirements-test.txt")

    discrepancias = {
        nombre: (produccion[nombre], pruebas[nombre])
        for nombre in set(produccion) & set(pruebas)
        if produccion[nombre] and pruebas[nombre] and produccion[nombre] != pruebas[nombre]
    }
    assert not discrepancias, (
        "Las pruebas correrían contra versiones distintas de las que usa producción: "
        f"{discrepancias}"
    )


def test_las_excepciones_declaradas_siguen_existiendo() -> None:
    """Si una excepción deja de ser dependencia, sobra: se elimina de la lista."""
    produccion = _paquetes("requirements-api.txt")
    sobrantes = sorted(set(SOLO_PRODUCCION) - set(produccion))
    assert not sobrantes, f"SOLO_PRODUCCION menciona paquetes que ya no se instalan: {sobrantes}"
