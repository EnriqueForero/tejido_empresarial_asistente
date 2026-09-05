"""
Capa de seguridad HTTP: tamaño de la solicitud, autenticación Basic opcional
y cabeceras de protección en toda respuesta.
"""
from __future__ import annotations

import base64
import secrets

from fastapi import FastAPI
from fastapi import Request as FastAPIRequest
from fastapi.responses import JSONResponse

from backend.comun import (
    ACCESS_CONTROL_ACTIVE,
    ACCESS_CONTROL_PARTIAL,
    ACCESS_PASSWORD,
    ACCESS_USER,
    MAX_REQUEST_BYTES,
)

REALM = 'Basic realm="Tejido Empresarial", charset="UTF-8"'


def valid_basic_credentials(request: FastAPIRequest) -> bool:
    authorization = request.headers.get("authorization", "")
    try:
        scheme, token = authorization.split(" ", 1)
        if scheme.casefold() != "basic":
            return False
        decoded = base64.b64decode(token, validate=True).decode("utf-8")
        username, separator, password = decoded.partition(":")
        return (
            bool(separator)
            and secrets.compare_digest(username.encode("utf-8"), ACCESS_USER.encode("utf-8"))
            and secrets.compare_digest(password.encode("utf-8"), ACCESS_PASSWORD.encode("utf-8"))
        )
    except (TypeError, ValueError, UnicodeDecodeError):
        return False


def instalar(app: FastAPI) -> None:
    """Registra la capa de seguridad en la aplicación."""

    @app.middleware("http")
    async def security_layer(request: FastAPIRequest, call_next):
        content_length = request.headers.get("content-length")
        is_health = request.url.path == "/api/health"
        # Sin `Content-Length` no hay nada que comparar: una petición troceada
        # (Transfer-Encoding: chunked) pasaba de largo el tope. Los métodos con
        # cuerpo tienen que declarar su tamaño.
        sin_tamano = (
            request.method in ("POST", "PUT", "PATCH")
            and not content_length
            and "chunked" in request.headers.get("transfer-encoding", "").lower()
        )
        if sin_tamano:
            response = JSONResponse(
                {"detail": "La solicitud debe declarar su tamaño (Content-Length)."}, status_code=411
            )
        elif content_length and content_length.isdigit() and int(content_length) > MAX_REQUEST_BYTES:
            response = JSONResponse({"detail": "La solicitud supera el tamaño permitido."}, status_code=413)
        elif ACCESS_CONTROL_PARTIAL and not is_health:
            response = JSONResponse({"detail": "El control de acceso está configurado de forma incompleta."}, status_code=503)
        elif ACCESS_CONTROL_ACTIVE and not is_health and not valid_basic_credentials(request):
            response = JSONResponse({"detail": "Autenticación requerida."}, status_code=401, headers={"WWW-Authenticate": REALM})
        else:
            response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; base-uri 'self'; object-src 'none'; frame-ancestors 'self'; "
            "form-action 'self'; img-src 'self' data: blob:; font-src 'self' data:; style-src 'self' 'unsafe-inline'; "
            "script-src 'self'; connect-src 'self'"
        )
        # HSTS sólo cuando la petición llegó por HTTPS (Railway lo indica en X-Forwarded-Proto);
        # en local, por HTTP, la cabecera sería ignorada o contraproducente.
        if request.headers.get("x-forwarded-proto", request.url.scheme) == "https":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        if request.url.path.startswith("/assets/"):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        elif request.url.path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")
        return response
