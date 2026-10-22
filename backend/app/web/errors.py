"""Friendly bilingual full-page fallbacks for 404/500/503 (never a raw error or stack trace).

Only browsers navigating to a page get HTML; API, static and webhook callers keep the JSON
error bodies they parse.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import Response
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend.app.core.messages import get_message
from backend.app.web.teacher import templates

logger = logging.getLogger("abhyas.web.errors")

# Gateway statuses are shown as the 503 "waking up" page
_PAGE_FOR_STATUS = {404: 404, 500: 500, 502: 503, 503: 503, 504: 503}
_NON_PAGE_PREFIXES = ("/api/", "/static/", "/whatsapp", "/webhook", "/healthz", "/health")


def _wants_page(request: Request) -> bool:
    path = request.url.path
    if path.startswith(_NON_PAGE_PREFIXES):
        return False
    return "text/html" in request.headers.get("accept", "")


def _texts(code: int) -> dict[str, str]:
    """Both languages are always shown, whatever the UI language is."""
    if code == 404:
        return {
            "title_hi": get_message("ui_error_404_title", lang="hi"),
            "body_hi": get_message("ui_error_404_body", lang="hi"),
            "title_en": get_message("ui_error_404_title", lang="en"),
            "body_en": get_message("ui_error_404_body", lang="en"),
        }
    if code == 503:
        return {
            "title_hi": get_message("ui_error_503_title", lang="hi"),
            "body_hi": get_message("ui_error_503_body", lang="hi"),
            "title_en": get_message("ui_error_503_title", lang="en"),
            "body_en": get_message("ui_error_503_body", lang="en"),
        }
    return {
        "title_hi": get_message("ui_error_500_title", lang="hi"),
        "body_hi": get_message("ui_error_500_body", lang="hi"),
        "title_en": get_message("ui_error_500_title", lang="en"),
        "body_en": get_message("ui_error_500_body", lang="en"),
    }


def render_error_page(request: Request, status_code: int) -> Response:
    code = _PAGE_FOR_STATUS.get(status_code, 500)
    return templates.TemplateResponse(
        request=request,
        name="error.html",
        context={"code": code, **_texts(code)},
        status_code=status_code,
    )


def install_error_pages(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException) -> Response:
        if exc.status_code in _PAGE_FOR_STATUS and _wants_page(request):
            return render_error_page(request, exc.status_code)
        return await http_exception_handler(request, exc)

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> Response:
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        if _wants_page(request):
            return render_error_page(request, 500)
        return Response(
            '{"detail":"Internal Server Error"}', status_code=500, media_type="application/json"
        )


__all__ = ["install_error_pages", "render_error_page"]
