"""
API del aplicativo Tejido Empresarial (FastAPI): ensamblaje.

Un único proceso sirve la API (/api/*) y el frontend React compilado
(frontend/dist). Este archivo sólo arma la aplicación: la configuración de
ejecución vive en `backend/comun.py`, la capa de seguridad en
`backend/middleware.py` y cada dominio en su router (`backend/routers/`).
La conexión a Snowflake, las consultas y la auditoría conservan la lógica del
aplicativo Streamlit original; el navegador nunca recibe credenciales ni SQL.
"""
from __future__ import annotations

import logging
import os
import sys
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

# Los mensajes van a stdout para que aparezcan en los registros de Railway.
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s · %(message)s",
    stream=sys.stdout,
)

from backend import comun, middleware  # noqa: E402 - después de configurar el registro
from backend.comun import ACCESS_CONTROL_ACTIVE, ACCESS_CONTROL_PARTIAL, APP_ENV, DEMO_MODE, FRONTEND_DIST, logger  # noqa: E402
from backend.config import APP_TITLE, APP_VERSION  # noqa: E402
from backend.routers import asistente, empresas, recursos, salud  # noqa: E402


@asynccontextmanager
async def ciclo_de_vida(_app: FastAPI) -> AsyncIterator[None]:
    # Abre la sesión de Snowflake en segundo plano al arrancar: la primera consulta
    # de cada despliegue no paga la conexión (2 a 4 s) y el usuario no la nota.
    if not DEMO_MODE:
        comun.snowflake.calentar()
    yield


app = FastAPI(
    title=APP_TITLE,
    version=APP_VERSION,
    docs_url="/api/docs" if APP_ENV != "production" else None,
    redoc_url=None,
    lifespan=ciclo_de_vida,
)

if ACCESS_CONTROL_PARTIAL:
    logger.warning("APP_BASIC_USER y APP_BASIC_PASSWORD deben configurarse juntos; el servicio responderá 503.")
elif not ACCESS_CONTROL_ACTIVE and not DEMO_MODE:
    logger.warning(
        "El aplicativo se sirve sin autenticación HTTP (igual que la versión Streamlit). "
        "Configure APP_BASIC_USER y APP_BASIC_PASSWORD para protegerlo; el README explica cómo."
    )

middleware.instalar(app)
app.include_router(salud.router)
app.include_router(empresas.router)
app.include_router(asistente.router)
if (FRONTEND_DIST / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")
# Los comodines (/api/{…} y la SPA) van de últimos: FastAPI resuelve en orden de registro.
app.include_router(recursos.router)
