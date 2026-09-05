"""Glosario, documentos institucionales y los comodines de API y SPA (se registran al final)."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response

from backend.comun import FRONTEND_DIST, MIME_XLSX, PUBLIC_ORIGIN
from backend.config import PERIODS
from backend.glossary import GLOSSARY_PATH, METHODOLOGY_PATH, load_glossary

router = APIRouter()


@router.get("/api/glossary")
def glossary() -> dict[str, Any]:
    return load_glossary()


@router.get("/api/resources/glossary.xlsx")
def glossary_file() -> FileResponse:
    return FileResponse(
        GLOSSARY_PATH,
        media_type=MIME_XLSX,
        filename=f"ProColombia_Glosario_Tejido_Empresarial_{PERIODS['glossary']}.xlsx",
    )


@router.get("/api/resources/methodology.docx")
def methodology_file() -> FileResponse:
    return FileResponse(
        METHODOLOGY_PATH,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename="ProColombia_Metodologia_Tejido_Empresarial.docx",
    )


@router.api_route("/api/{unknown_path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"], include_in_schema=False)
def unknown_api_route(unknown_path: str) -> JSONResponse:
    return JSONResponse({"detail": "Ruta de API no encontrada."}, status_code=404)


# ── Frontend compilado (SPA) ──────────────────────────────────────────────
def _index_html() -> str:
    index_path = FRONTEND_DIST / "index.html"
    if not index_path.is_file():
        return "<!doctype html><meta charset='utf-8'><h1>Frontend no compilado</h1><p>Ejecute <code>npm run build</code> en <code>frontend/</code>.</p>"
    html = index_path.read_text(encoding="utf-8")
    if PUBLIC_ORIGIN.startswith(("https://", "http://localhost", "http://127.0.0.1")):
        return html.replace("__PUBLIC_ORIGIN__", PUBLIC_ORIGIN)
    return (
        html.replace('<meta property="og:image" content="__PUBLIC_ORIGIN__/og.png" />', "")
        .replace('<meta name="twitter:image" content="__PUBLIC_ORIGIN__/og.png" />', "")
    )


@router.get("/{full_path:path}", include_in_schema=False, response_model=None)
def spa(full_path: str) -> Response:
    if full_path:
        candidate = (FRONTEND_DIST / full_path).resolve()
        if candidate.is_file() and FRONTEND_DIST.resolve() in candidate.parents:
            return FileResponse(candidate)
    return HTMLResponse(_index_html())
