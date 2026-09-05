"""
Contrato de rutas: la lista de endpoints es parte de la interfaz pública.

Al repartir `main.py` en routers, una ruta puede perderse o registrarse en un
orden que la deje detrás de un comodín sin que ninguna otra prueba lo note.
Esta fija la lista exacta y el orden de los comodines.
"""
from __future__ import annotations

import os

os.environ["APP_DEMO_MODE"] = "true"
os.environ["APP_ENV"] = "development"

from fastapi.routing import APIRoute  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

RUTAS_PUBLICAS = {
    ("GET", "/api/health"),
    ("GET", "/api/diagnostico"),
    ("GET", "/api/metadata"),
    ("POST", "/api/filters/options"),
    ("POST", "/api/companies/search"),
    ("GET", "/api/companies/{nit}"),
    ("POST", "/api/companies/export"),
    ("GET", "/api/ia/estado"),
    ("POST", "/api/ia/preguntar"),
    ("POST", "/api/ia/exportar/excel"),
    ("POST", "/api/ia/exportar/pptx"),
    ("POST", "/api/ia/exportar/empresas"),
    ("GET", "/api/glossary"),
    ("GET", "/api/resources/glossary.xlsx"),
    ("GET", "/api/resources/methodology.docx"),
}


def _rutas():
    from backend.main import app

    return [ruta for ruta in app.routes if isinstance(ruta, APIRoute)]


def test_la_lista_de_rutas_publicas_es_exactamente_la_esperada() -> None:
    publicas = {(metodo, ruta.path) for ruta in _rutas() if ruta.include_in_schema for metodo in ruta.methods}
    assert publicas == RUTAS_PUBLICAS


def test_los_comodines_se_registran_despues_de_todas_las_rutas() -> None:
    caminos = [ruta.path for ruta in _rutas()]
    comodin_api = caminos.index("/api/{unknown_path:path}")
    comodin_spa = caminos.index("/{full_path:path}")
    ultima_api = max(i for i, camino in enumerate(caminos) if camino.startswith("/api/") and "{unknown_path" not in camino)
    assert ultima_api < comodin_api < comodin_spa


def test_el_comodin_de_api_responde_404_y_la_spa_sirve_el_resto() -> None:
    from backend.main import app

    cliente = TestClient(app)
    assert cliente.get("/api/no-existe").status_code == 404
    assert cliente.post("/api/tampoco").status_code == 404
    pagina = cliente.get("/asistente")
    assert pagina.status_code == 200 and "text/html" in pagina.headers["content-type"]


def test_las_cabeceras_de_seguridad_llegan_en_toda_respuesta() -> None:
    from backend.main import app

    cliente = TestClient(app)
    respuesta = cliente.get("/api/health", headers={"x-forwarded-proto": "https"})
    for cabecera in ("Content-Security-Policy", "X-Content-Type-Options", "X-Frame-Options", "Referrer-Policy", "Cross-Origin-Opener-Policy", "Strict-Transport-Security"):
        assert cabecera in respuesta.headers, cabecera
    assert respuesta.headers["Cache-Control"] == "no-store"
    # Sin HTTPS no se promete HSTS: en local sería contraproducente.
    assert "Strict-Transport-Security" not in cliente.get("/api/health").headers
