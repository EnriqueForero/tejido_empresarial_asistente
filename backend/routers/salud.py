"""Estado del servicio (/api/health) y diagnóstico paso a paso (/api/diagnostico)."""
from __future__ import annotations

import secrets
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi import Request as FastAPIRequest

from backend import comun
from backend.comun import ACCESS_CONTROL_ACTIVE, ACCESS_CONTROL_PARTIAL, APP_ENV, DEMO_MODE, DIAG_TOKEN, FRONTEND_DIST, logger
from backend.config import APP_VERSION
from backend.middleware import REALM, valid_basic_credentials
from backend.routers.asistente import telemetria_ia

router = APIRouter()


@router.get("/api/health")
def health(request: FastAPIRequest, deep: bool = False) -> dict[str, Any]:
    if ACCESS_CONTROL_PARTIAL:
        raise HTTPException(status_code=503, detail="Configure APP_BASIC_USER y APP_BASIC_PASSWORD juntos.")
    if deep and ACCESS_CONTROL_ACTIVE and not valid_basic_credentials(request):
        raise HTTPException(
            status_code=401,
            detail="Autenticación requerida para el health profundo.",
            headers={"WWW-Authenticate": REALM},
        )
    snowflake = comun.snowflake
    reporte = snowflake.configuration_report()
    if DEMO_MODE:
        connection = "demo"
    elif not snowflake.configured:
        connection = "missing_configuration"
    elif reporte["last_error"]:
        connection = "error"
    elif reporte["verified"]:
        # Ya hubo un apretón de manos correcto en este proceso.
        connection = "connected"
    else:
        # Configuración completa, pero todavía sin ninguna consulta: no se puede
        # afirmar que esté conectado. La página /estado resuelve esto con ?deep=true.
        connection = "configured"
    if deep and not DEMO_MODE and snowflake.configured:
        try:
            snowflake.verificar()
            connection = "connected"
        except Exception as exc:  # noqa: BLE001
            logger.exception("Health profundo: Snowflake no respondió")
            raise HTTPException(
                status_code=503,
                detail=(
                    "Snowflake está configurado, pero no respondió. "
                    "Consulte /api/diagnostico para ver en qué paso falla."
                ),
            ) from exc
        reporte = snowflake.configuration_report()
    return {
        "status": "ok",
        "version": APP_VERSION,
        "data_connection": connection,
        "access_control": "basic" if ACCESS_CONTROL_ACTIVE else "open",
        "frontend_built": (FRONTEND_DIST / "index.html").is_file(),
        "demo_mode": DEMO_MODE,
        "snowflake": {
            "connector_installed": reporte["connector_installed"],
            "connector_version": reporte["connector_version"],
            "pandas_arrow": reporte["pandas_arrow"],
            "missing_variables": reporte["missing_variables"],
            "key_sources": reporte["key_sources"],
            # Sólo si hubo un fallo de conexión; el detalle vive en /api/diagnostico.
            "connection_error": bool(reporte["last_error"]),
            "verified": reporte["verified"],
            "verified_at": reporte["verified_at"],
        },
    }


@router.get("/api/diagnostico")
def diagnostico(request: FastAPIRequest, token: str = "") -> dict[str, Any]:
    """Revisa paso a paso entorno → conector → llave → sesión → tablas → asistente.

    Devuelve el error real de cada paso, sin secretos. Para que no quede abierto
    en un despliegue público exige una de tres condiciones: autenticación HTTP
    Basic activa (el middleware ya la valida), APP_DIAG_TOKEN correcto (por la
    cabecera X-Diag-Token o, por compatibilidad, en la URL), o APP_ENV=development.
    """
    entregado = request.headers.get("x-diag-token", "") or token
    autorizado = (
        ACCESS_CONTROL_ACTIVE
        or APP_ENV != "production"
        # `compare_digest` sobre texto exige ASCII: se comparan bytes para que un
        # token con acentos responda 403 y no un error interno.
        or (DIAG_TOKEN and secrets.compare_digest(entregado.encode("utf-8"), DIAG_TOKEN.encode("utf-8")))
    )
    if not autorizado:
        raise HTTPException(
            status_code=403,
            detail=(
                "El diagnóstico está cerrado en producción. Active una de estas opciones en "
                "Railway y vuelva a intentarlo: (1) APP_BASIC_USER y APP_BASIC_PASSWORD "
                "—recomendado, protege todo el aplicativo—, o (2) APP_DIAG_TOKEN y llame a "
                "/api/diagnostico?token=EL_MISMO_VALOR."
            ),
        )
    if DEMO_MODE:
        return {
            "modo": "demo",
            "resumen": "El aplicativo está en modo demostración: no consulta Snowflake.",
            "siguiente_paso": "Quite APP_DEMO_MODE (o póngala en false) para usar datos reales.",
            "pasos": [],
        }

    pasos = comun.snowflake.diagnostico()
    fallo = next((paso for paso in pasos if not paso["ok"]), None)
    if fallo:
        logger.error("Diagnóstico: falló el paso '%s' — %s", fallo["paso"], fallo.get("error"))
    return {
        "modo": "snowflake",
        "version": APP_VERSION,
        "todo_ok": fallo is None,
        "resumen": (
            "Todos los pasos respondieron correctamente."
            if fallo is None
            else f"Primer fallo en el paso «{fallo['paso']}»: {fallo.get('error')}"
        ),
        "siguiente_paso": sugerencia(fallo),
        "pasos": pasos,
        # Cuántos registros del asistente entraron y cuántos se perdieron: si la
        # tabla de métricas no existe, aquí se ve sin abrir Snowflake.
        "telemetria": telemetria_ia().estado(),
    }


def sugerencia(fallo: dict[str, Any] | None) -> str:
    """Qué hacer según el paso que falló (lenguaje operativo, no técnico)."""
    if fallo is None:
        return "Nada pendiente: la conexión y las tablas responden."
    consejos = {
        "entorno": "Complete en Railway las variables que aparecen como faltantes y redespliegue.",
        "conector": "La imagen no trae el conector: revise que el build usara requirements-api.txt.",
        "llave_1": "Regenere el valor con [Convert]::ToBase64String([IO.File]::ReadAllBytes(\"rsa_key_1.der\")) "
                   "y péguelo en UNA sola línea, sin comillas ni saltos. Verifique la frase en SF_PRIVATE_KEY_PASSPHRASE_1.",
        "llave_2": "Misma revisión para la llave de respaldo, o retire SF_PRIVATE_KEY_B64_2 si no la usa.",
        "sesion": "Snowflake rechazó la conexión. Causas típicas: la llave pública no está registrada en el "
                  "usuario (ALTER USER … SET RSA_PUBLIC_KEY), el rol o el warehouse no existen, o una política "
                  "de red bloquea la IP de Railway. El texto del error lo precisa.",
        "consulta_simple": "La sesión abre pero no ejecuta consultas: revise que el warehouse esté activo y con crédito.",
        "tabla_filtros_generales": "El rol no ve la tabla de filtros: conceda SELECT sobre el esquema SEGMENTACION.",
        "tabla_filtros_exportadoras": "El rol no ve FILTROS_EXPORTADORAS: conceda SELECT sobre el esquema.",
        "tabla_empresas": "El rol no ve la tabla de empresas: conceda SELECT sobre TEJIDO_EMPRESARIAL_COMPLETO_BASE_MUNICIPIOS_P.",
        "tabla_bienes": "El rol no ve PUBLIC.BIENES_Y_SERVICIOS_P: sin ella fallan los filtros de exportación.",
        "tabla_eventos": "Sólo afecta la auditoría; el aplicativo funciona igual. Conceda INSERT en SEGUIMIENTO.EVENTOS.",
        "consulta_vista_previa": "La consulta real falló. Si el mensaje habla de una dependencia opcional "
                                 "(«Optional dependency: pandas»), la imagen se construyó sin pyarrow: "
                                 "requirements-api.txt debe instalar snowflake-snowpark-python[pandas]. "
                                 "Si habla de permisos, conceda SELECT sobre las columnas o la tabla.",
        "vista_semantica": "El rol no ve la vista semántica del asistente. Ejecute snowflake/01_permisos_asistente.sql "
                           "(GRANT SELECT ON SEMANTIC VIEW …) o revise que SF_SEMANTIC_VIEW tenga el nombre completo.",
        "tabla_asistente_log": "Sólo afecta las métricas del asistente; las respuestas funcionan igual. Ejecute "
                               "snowflake/03_telemetria_asistente.sql para crear las tablas y conceder INSERT.",
        "cortex_complete": "La redacción con IA no responde con este modelo: el asistente entrega el resumen automático "
                           "de los datos. Lea el error del paso: si habla de privilegios, ejecute el GRANT de "
                           "SNOWFLAKE.CORTEX_USER; si dice que el modelo no existe o no está disponible en la región, "
                           "cambie SF_CORTEX_MODEL (ver snowflake/02_comparar_modelos.sql).",
    }
    return consejos.get(fallo["paso"], "Revise el mensaje de error del paso indicado.")
