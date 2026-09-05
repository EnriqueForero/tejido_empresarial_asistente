"""Estado del servicio (/api/health) y diagnóstico paso a paso (/api/diagnostico)."""
from __future__ import annotations

import secrets
import threading
import time
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi import Request as FastAPIRequest

from backend import comun
from backend.comun import ACCESS_CONTROL_ACTIVE, ACCESS_CONTROL_PARTIAL, APP_ENV, DEMO_MODE, DIAG_TOKEN, FRONTEND_DIST, logger
from backend.config import APP_VERSION
from backend.middleware import REALM, valid_basic_credentials
from backend.routers.asistente import telemetria_ia

router = APIRouter()

#: Segundos entre dos pruebas reales de Cortex. La prueba llama al modelo, es
#: decir gasta créditos, y en una cuenta mal configurada tarda más de un minuto.
#: Con el diagnóstico abierto —que es como está el servicio de ProColombia— sin
#: esto cualquiera podría pedirla en bucle. El propietario no lo nota: pulsar el
#: botón dos veces seguidas devuelve el mismo resultado, y lo dice.
PAUSA_ENTRE_PRUEBAS_CORTEX = 300.0
_candado_cortex = threading.Lock()
_ultima_prueba_cortex: dict[str, Any] = {"cuando": 0.0, "paso": None}


def _prueba_cortex_reciente(reloj: float) -> dict[str, Any] | None:
    """El resultado de la última prueba si aún vale; si no, None (y se marca en curso)."""
    with _candado_cortex:
        paso = _ultima_prueba_cortex["paso"]
        if paso is not None and reloj - float(_ultima_prueba_cortex["cuando"]) < PAUSA_ENTRE_PRUEBAS_CORTEX:
            hace = int(reloj - float(_ultima_prueba_cortex["cuando"]))
            copia = dict(paso)
            copia["detalle"] = {
                **(copia.get("detalle") or {}),
                "reutilizado": True,
                "nota": (
                    f"Resultado de la prueba hecha hace {hace} s. La prueba llama al modelo y gasta "
                    f"créditos, así que se repite como mucho cada {int(PAUSA_ENTRE_PRUEBAS_CORTEX / 60)} minutos."
                ),
            }
            return copia
        return None


def _guardar_prueba_cortex(paso: dict[str, Any] | None, reloj: float) -> None:
    if paso is None:
        return
    with _candado_cortex:
        _ultima_prueba_cortex["paso"] = dict(paso)
        _ultima_prueba_cortex["cuando"] = reloj


#: Nombres con los que responde un equipo de desarrollo. En un portátil, correr
#: en modo desarrollo es lo normal y no hay nada que avisar.
_LOCALES = ("localhost", "127.0.0.1", "[::1]", "testserver", "0.0.0.0")


def _publicado(request: FastAPIRequest | None) -> bool:
    """¿La petición llega por un dominio público, o desde un equipo de desarrollo?"""
    anfitrion = (request.headers.get("host", "") if request else "").split(":")[0].lower()
    return bool(anfitrion) and not any(anfitrion.startswith(local) for local in _LOCALES)


def paso_exposicion(request: FastAPIRequest | None = None) -> dict[str, Any]:
    """¿Está el servicio publicado, abierto a cualquiera y además en modo desarrollo?

    Se comprueba aquí y no en Snowflake porque es una propiedad del despliegue.
    Un servicio con `APP_ENV` distinto de «production» publica `/api/docs` y deja
    este mismo diagnóstico sin credenciales; en el dominio de Railway eso lo ve
    cualquiera con el enlace, y en un portátil no importa.
    """
    publicado = _publicado(request)
    en_desarrollo = APP_ENV != "production"
    protegido = ACCESS_CONTROL_ACTIVE or bool(DIAG_TOKEN)
    if publicado and en_desarrollo and not ACCESS_CONTROL_ACTIVE:
        detalle = {
            "app_env": APP_ENV,
            "acceso": "abierto" if not ACCESS_CONTROL_ACTIVE else "usuario y contraseña",
            "que_queda_publico": ["/api/docs", "/api/diagnostico", "/api/diagnostico?cortex=1"],
        }
        return {
            "paso": "exposicion",
            "descripcion": "Modo del despliegue y quién puede ver el diagnóstico",
            "ok": False,
            "detalle": detalle,
            "error": (
                f"El servicio corre con APP_ENV='{APP_ENV}' y sin usuario ni contraseña: la documentación "
                "de la API y este diagnóstico están abiertos a cualquiera con el enlace. En Railway → "
                "Variables, quite APP_ENV (o póngala en 'production'). Para conservar esta página, "
                "configure APP_BASIC_USER y APP_BASIC_PASSWORD, o APP_DIAG_TOKEN."
            ),
            "segundos": 0.0,
        }
    return {
        "paso": "exposicion",
        "descripcion": "Modo del despliegue y quién puede ver el diagnóstico",
        "ok": True,
        "detalle": {
            "app_env": APP_ENV,
            "acceso": "usuario y contraseña" if ACCESS_CONTROL_ACTIVE else "abierto",
            "diagnostico": "protegido" if protegido else "abierto (APP_ENV=production lo cierra)",
        },
        "segundos": 0.0,
    }


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
def diagnostico(request: FastAPIRequest, token: str = "", cortex: bool = False, reconectar: bool = False) -> dict[str, Any]:
    """Revisa paso a paso entorno → conector → llave → sesión → tablas → asistente.

    Devuelve el error real de cada paso, sin secretos. Para que no quede abierto
    en un despliegue público exige una de tres condiciones: autenticación HTTP
    Basic activa (el middleware ya la valida), APP_DIAG_TOKEN correcto (por la
    cabecera X-Diag-Token o, por compatibilidad, en la URL), o APP_ENV=development.
    """
    entregado = request.headers.get("x-diag-token", "") or token
    # `compare_digest` sobre texto exige ASCII: se comparan bytes para que un
    # token con acentos responda 403 y no un error interno.
    con_credencial = ACCESS_CONTROL_ACTIVE or bool(
        DIAG_TOKEN and secrets.compare_digest(entregado.encode("utf-8"), DIAG_TOKEN.encode("utf-8"))
    )
    # En un anfitrión publicado, `APP_ENV` no basta. Se comprobó en producción:
    # con APP_ENV distinto de «production» este diagnóstico quedaba abierto a
    # cualquiera con el enlace, y con él once consultas al warehouse, el cierre
    # de la sesión compartida y —con ?cortex=1— créditos de IA. En un portátil no
    # cambia nada: `testserver` y `localhost` siguen entrando sin credencial.
    autorizado = con_credencial or (APP_ENV != "production" and not _publicado(request))
    if not autorizado:
        raise HTTPException(
            status_code=403,
            detail=(
                "El diagnóstico necesita credenciales en un servicio publicado. En Railway → "
                "Variables, configure una de estas dos opciones y vuelva a intentarlo: "
                "(1) APP_BASIC_USER y APP_BASIC_PASSWORD —lo recomendado, porque protegen todo "
                "el aplicativo—, o (2) APP_DIAG_TOKEN con un valor largo que usted elija, y "
                "entre por /estado?token=EL_MISMO_VALOR."
            ),
        )
    if DEMO_MODE:
        return {
            "modo": "demo",
            "resumen": "El aplicativo está en modo demostración: no consulta Snowflake.",
            "siguiente_paso": "Quite APP_DEMO_MODE (o póngala en false) para usar datos reales.",
            "pasos": [],
        }

    reloj = time.monotonic()
    reciente = _prueba_cortex_reciente(reloj) if cortex else None
    pasos = [paso_exposicion(request), *comun.snowflake.diagnostico(probar_cortex=cortex and reciente is None, reconectar=reconectar)]
    if cortex:
        indice = next((i for i, paso in enumerate(pasos) if paso["paso"] == "cortex_complete"), None)
        if indice is not None:
            if reciente is not None:
                pasos[indice] = reciente
            else:
                _guardar_prueba_cortex(pasos[indice], reloj)
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
        "exposicion": "En Railway → Variables, quite APP_ENV (o póngala en «production»): así dejan de ser "
                      "públicas la documentación de la API y esta misma página. Para seguir viendo el "
                      "diagnóstico, configure APP_BASIC_USER y APP_BASIC_PASSWORD —que además protegen todo "
                      "el aplicativo— o, como mínimo, APP_DIAG_TOKEN y entre por /estado?token=EL_VALOR.",
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
        "cortex_region": "Sólo informativo: dice en qué región está la cuenta y si tiene habilitada la inferencia "
                         "entre regiones, que es lo que permite usar modelos de Cortex alojados en otra región.",
        "cortex_complete": "La redacción con IA no responde con este modelo: el asistente entrega el resumen automático "
                           "de los datos. Lea el error del paso: si habla de privilegios, ejecute el GRANT de "
                           "SNOWFLAKE.CORTEX_USER; si dice que el modelo no existe o no está disponible en la región, "
                           "cambie SF_CORTEX_MODEL (ver snowflake/02_comparar_modelos.sql).",
    }
    return consejos.get(fallo["paso"], "Revise el mensaje de error del paso indicado.")
