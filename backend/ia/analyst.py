"""
Cliente REST de Snowflake Cortex Analyst (pregunta en español → SQL).

Envía la pregunta y la vista semántica desplegada al endpoint
``/api/v2/cortex/analyst/message`` y devuelve la SQL propuesta. La
autenticación es la misma llave RSA que ya usa el conector del aplicativo: no
hay que configurar ningún secreto nuevo en Railway.

Documentación: https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-analyst
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any

import requests

from backend.config import IA_ANALYST_TIMEOUT, SEMANTIC_VIEW
from backend.database import redactar, snowflake

logger = logging.getLogger("tejido.ia")

#: Snowflake exige menos de una hora; se renueva con margen.
_VIGENCIA_JWT = 55 * 60
_MARGEN_RENOVACION = 5 * 60


class ErrorAnalyst(RuntimeError):
    """Cortex Analyst no respondió o respondió algo que no se puede usar."""


def cuenta_para_jwt(cuenta: str) -> str:
    """Identificador de cuenta en el formato que exige el JWT de Snowflake.

    Para cuentas normales se recorta en el primer punto (``my17686.us-east-2.aws``
    → ``MY17686``); para cuentas *global* se recorta en el primer guion.
    """
    valor = (cuenta or "").strip()
    if ".global" in valor.lower():
        corte = valor.find("-")
    else:
        corte = valor.find(".")
    if corte > 0:
        valor = valor[:corte]
    return valor.upper()


def host_rest(cuenta: str) -> str:
    """Host de la API REST. ``SF_HOST`` lo sobreescribe si la cuenta es especial."""
    explicito = os.getenv("SF_HOST", "").strip()
    if explicito:
        return explicito.replace("https://", "").replace("http://", "").rstrip("/")
    base = (cuenta or "").strip().rstrip(".")
    return f"{base}.snowflakecomputing.com".replace("_", "-").lower()


class GeneradorJWT:
    """Firma y cachea el token de la API REST con la llave privada del aplicativo."""

    def __init__(self) -> None:
        self._token = ""
        self._expira = 0.0

    def _firmar(self) -> str:
        import jwt as pyjwt

        llave, huella = snowflake.material_jwt()
        cuenta = os.getenv("SF_ACCOUNT", "")
        usuario = os.getenv("SF_USER", "")
        if not cuenta or not usuario:
            raise ErrorAnalyst("Faltan SF_ACCOUNT o SF_USER para firmar el token de Cortex.")
        calificado = f"{cuenta_para_jwt(cuenta)}.{usuario.upper()}"
        ahora = int(time.time())
        carga = {
            "iss": f"{calificado}.{huella}",
            "sub": calificado,
            "iat": ahora,
            "exp": ahora + _VIGENCIA_JWT,
        }
        return pyjwt.encode(carga, llave, algorithm="RS256")

    def token(self) -> str:
        if not self._token or time.time() > self._expira - _MARGEN_RENOVACION:
            self._token = self._firmar()
            self._expira = time.time() + _VIGENCIA_JWT
        return self._token


@dataclass
class RespuestaAnalyst:
    """Lo que Cortex Analyst devolvió para una pregunta."""

    sql: str = ""
    interpretacion: str = ""
    sugerencias: list[str] = field(default_factory=list)
    advertencias: list[str] = field(default_factory=list)
    request_id: str = ""
    contenido_crudo: list[dict[str, Any]] = field(default_factory=list)


def parsear_respuesta(cuerpo: dict[str, Any]) -> RespuestaAnalyst:
    """Extrae SQL, texto y sugerencias del cuerpo JSON, sin confiar en su forma."""
    salida = RespuestaAnalyst(request_id=str(cuerpo.get("request_id", "")))
    mensaje = cuerpo.get("message") or {}
    contenido = mensaje.get("content") or []
    if isinstance(contenido, list):
        salida.contenido_crudo = [bloque for bloque in contenido if isinstance(bloque, dict)]
        for bloque in salida.contenido_crudo:
            tipo = bloque.get("type")
            if tipo == "sql" and not salida.sql:
                salida.sql = str(bloque.get("statement", "")).strip()
            elif tipo == "text":
                salida.interpretacion = (salida.interpretacion + "\n" + str(bloque.get("text", ""))).strip()
            elif tipo == "suggestions":
                for sugerencia in bloque.get("suggestions") or []:
                    salida.sugerencias.append(str(sugerencia))
    for aviso in cuerpo.get("warnings") or []:
        salida.advertencias.append(str(aviso.get("message", aviso)) if isinstance(aviso, dict) else str(aviso))
    return salida


class ClienteAnalyst:
    """Pregunta a Cortex Analyst contra la vista semántica configurada."""

    RUTA = "/api/v2/cortex/analyst/message"

    def __init__(self, vista_semantica: str = SEMANTIC_VIEW, timeout: int = IA_ANALYST_TIMEOUT) -> None:
        self._vista = vista_semantica
        self._timeout = timeout
        self._jwt = GeneradorJWT()

    @property
    def vista_semantica(self) -> str:
        return self._vista

    def _cabeceras(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._jwt.token()}",
            "X-Snowflake-Authorization-Token-Type": "KEYPAIR_JWT",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def preguntar(self, pregunta: str, historial: list[dict[str, Any]] | None = None) -> RespuestaAnalyst:
        """Envía la pregunta (con el historial de la conversación) y devuelve la SQL.

        Raises:
            ErrorAnalyst: si falla la autenticación, la red o el servicio.
        """
        mensajes = list(historial or [])
        mensajes.append({"role": "user", "content": [{"type": "text", "text": pregunta}]})
        cuerpo = {"messages": mensajes, "semantic_view": self._vista}
        url = f"https://{host_rest(os.getenv('SF_ACCOUNT', ''))}{self.RUTA}"
        try:
            respuesta = requests.post(url, json=cuerpo, headers=self._cabeceras(), timeout=self._timeout)
        except requests.RequestException as exc:
            raise ErrorAnalyst(f"No fue posible contactar a Cortex Analyst: {redactar(exc)}") from exc
        if respuesta.status_code != 200:
            raise ErrorAnalyst(_mensaje_http(respuesta.status_code, respuesta.text))
        try:
            return parsear_respuesta(respuesta.json())
        except ValueError as exc:
            raise ErrorAnalyst("Cortex Analyst devolvió una respuesta que no es JSON.") from exc


def _mensaje_http(codigo: int, texto: str) -> str:
    """Traduce los códigos frecuentes a una instrucción accionable."""
    detalle = redactar(texto)[:300]
    if codigo == 401:
        return (
            "Snowflake rechazó las credenciales del asistente (401). La llave privada es la misma del "
            "aplicativo, así que revise que SF_USER sea el usuario dueño de la llave pública registrada "
            f"con ALTER USER … SET RSA_PUBLIC_KEY. Detalle: {detalle}"
        )
    if codigo == 403:
        return (
            "El rol no tiene permiso para usar Cortex (403). Ejecute en Snowflake: "
            "GRANT DATABASE ROLE SNOWFLAKE.CORTEX_USER TO ROLE <rol de la aplicación>; y conceda "
            f"SELECT sobre la vista semántica. Detalle: {detalle}"
        )
    if codigo == 404:
        return (
            "No se encontró la vista semántica configurada (404). Verifique SF_SEMANTIC_VIEW y que la "
            f"vista exista con DESCRIBE SEMANTIC VIEW. Detalle: {detalle}"
        )
    if codigo == 429:
        return "Cortex Analyst está limitando las solicitudes (429). Intente de nuevo en unos segundos."
    return f"Cortex Analyst respondió HTTP {codigo}: {detalle}"
