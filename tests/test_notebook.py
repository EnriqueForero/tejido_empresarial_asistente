"""
El notebook de publicación se comprueba aquí, no en Colab.

Cinco publicaciones se han roto por la misma razón: algo que sólo se validaba al
publicar —una dependencia, un archivo renombrado— y que en el equipo de
desarrollo no se notaba. Estas pruebas leen el cuaderno como datos (sin
ejecutarlo) y comprueban que su configuración siga de acuerdo con el proyecto:
si alguien renombra una prueba o agrega una dependencia, el fallo aparece al
ejecutar `pytest`, que es donde está la causa.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

import pytest

RAIZ = Path(__file__).resolve().parent.parent
NOTEBOOK = RAIZ / "notebooks" / "Publicacion_GitHub_TejidoEmpresarial.ipynb"


def _constantes(nombres: set[str]) -> dict[str, Any]:
    """Valores literales asignados en las celdas de código, sin ejecutar nada."""
    cuaderno = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    encontrados: dict[str, Any] = {}
    for celda in cuaderno["cells"]:
        if celda["cell_type"] != "code":
            continue
        fuente = "".join(celda["source"])
        if fuente.lstrip().startswith("%"):  # celdas con magias de Jupyter
            continue
        try:
            arbol = ast.parse(fuente)
        except SyntaxError:
            continue
        for nodo in arbol.body:
            if not isinstance(nodo, ast.Assign):
                continue
            for destino in nodo.targets:
                if isinstance(destino, ast.Name) and destino.id in nombres and destino.id not in encontrados:
                    try:
                        encontrados[destino.id] = ast.literal_eval(nodo.value)
                    except ValueError:
                        pass
    return encontrados


@pytest.fixture(scope="module")
def config() -> dict[str, Any]:
    datos = _constantes({"ARCHIVOS_REQUERIDOS", "COMANDOS_BUILD", "CARPETAS_EXCLUIDAS", "VERSION"})
    faltan = {"ARCHIVOS_REQUERIDOS", "COMANDOS_BUILD", "CARPETAS_EXCLUIDAS", "VERSION"} - set(datos)
    assert not faltan, f"No se pudieron leer del notebook: {sorted(faltan)}"
    return datos


def test_todo_archivo_exigido_por_el_notebook_existe(config: dict[str, Any]) -> None:
    """Un archivo renombrado y no actualizado en la lista aborta la publicación en Colab."""
    ausentes = [ruta for ruta in config["ARCHIVOS_REQUERIDOS"] if not (RAIZ / ruta).exists()]
    assert not ausentes, (
        "El notebook exige archivos que ya no existen; su pre-flight abortará la publicación: "
        f"{ausentes}. Actualice ARCHIVOS_REQUERIDOS en la Celda A."
    )


def test_las_pruebas_y_la_configuracion_del_proyecto_estan_en_la_lista(config: dict[str, Any]) -> None:
    """Lo que la integración continua necesita para correr tiene que viajar al repositorio."""
    exigidos = set(config["ARCHIVOS_REQUERIDOS"])
    imprescindibles = {
        *(f"tests/{ruta.name}" for ruta in sorted((RAIZ / "tests").glob("test_*.py"))),
        "tests/conftest.py",
        "tests/dobles.py",
        "pyproject.toml",
        "requirements-api.txt",
        "requirements-test.txt",
        "frontend/package.json",
        "frontend/package-lock.json",
        "frontend/vitest.config.ts",
    }
    faltan = sorted(imprescindibles - exigidos)
    assert not faltan, f"El notebook no exige archivos que el proyecto sí necesita: {faltan}"


def test_el_build_del_notebook_cubre_lo_mismo_que_la_integracion_continua(config: dict[str, Any]) -> None:
    """Si el cuaderno valida menos que la CI, el fallo aparece después de publicar."""
    comandos = " ".join(config["COMANDOS_BUILD"])
    for esperado in ("requirements-test.txt", "ruff check", "pytest", "npm ci", "npm test", "npm run build"):
        assert esperado in comandos, f"El build del notebook no ejecuta «{esperado}»."


def test_el_notebook_nunca_publica_cachés_ni_dependencias(config: dict[str, Any]) -> None:
    for carpeta in ("node_modules", "dist", "__pycache__", ".pytest_cache", ".ruff_cache", ".git"):
        assert carpeta in config["CARPETAS_EXCLUIDAS"], f"El notebook no excluye «{carpeta}»."


def test_la_version_del_notebook_coincide_con_la_del_aplicativo(config: dict[str, Any]) -> None:
    from backend.config import APP_VERSION

    paquete = json.loads((RAIZ / "frontend" / "package.json").read_text(encoding="utf-8"))
    candado = json.loads((RAIZ / "frontend" / "package-lock.json").read_text(encoding="utf-8"))
    assert config["VERSION"] == APP_VERSION == paquete["version"] == candado["version"], (
        f"notebook={config['VERSION']} · backend={APP_VERSION} · package.json={paquete['version']} · "
        f"package-lock.json={candado['version']}"
    )


def test_el_candado_de_npm_declara_lo_mismo_que_package_json() -> None:
    """`npm ci` falla en seco si se desvían: Colab, la CI y Railway lo usan."""
    paquete = json.loads((RAIZ / "frontend" / "package.json").read_text(encoding="utf-8"))
    candado = json.loads((RAIZ / "frontend" / "package-lock.json").read_text(encoding="utf-8"))
    raiz_candado = candado.get("packages", {}).get("", {})
    declaradas = {**paquete.get("dependencies", {}), **paquete.get("devDependencies", {})}
    en_candado = {**raiz_candado.get("dependencies", {}), **raiz_candado.get("devDependencies", {})}
    faltan = sorted(set(declaradas) - set(en_candado))
    assert not faltan, f"package-lock.json no está sincronizado; ejecute «npm install» en frontend/: {faltan}"
