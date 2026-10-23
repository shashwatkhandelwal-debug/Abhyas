"""UI language (Hindi default / English): request-scoped language, `/lang/<code>`, template helpers.

The chosen language lives in the `abhyas_lang` cookie (readable before login and by the offline page)
and, for signed-in users, in `app_user.ui_lang`. A tiny ASGI middleware copies the cookie into the
message catalog's context variable, so `get_message()` in templates and views is bilingual without
passing `lang` around. Both places are kept in step by `/lang/<code>` and by login.
"""

from __future__ import annotations

from typing import Annotated, Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import RedirectResponse
from jinja2 import pass_context
from markupsafe import Markup, escape
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.datastructures import Headers
from starlette.types import ASGIApp, Receive, Scope, Send

from backend.app.auth.guards import get_current_user_optional
from backend.app.config import settings
from backend.app.core.messages import (
    DEFAULT_LANG,
    LANG_COOKIE_NAME,
    SUPPORTED_LANGS,
    get_message,
    get_ui_lang,
    has_message,
    normalize_lang,
    reset_ui_lang,
    set_ui_lang,
)
from backend.app.db.models import AppUser
from backend.app.db.session import get_db_session
from backend.app.web.assets import sw_build_version

LANG_COOKIE_MAX_AGE = 365 * 24 * 3600

router = APIRouter(tags=["Language"])


def lang_from_cookie_header(cookie_header: str | None) -> str:
    """Language code from a raw Cookie header (default Hindi)."""
    for part in (cookie_header or "").split(";"):
        name, _, value = part.strip().partition("=")
        if name == LANG_COOKIE_NAME:
            return normalize_lang(value)
    return DEFAULT_LANG


class UiLangMiddleware:
    """Pure ASGI middleware: sets the message-catalog language for the request from the cookie."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return
        lang = lang_from_cookie_header(Headers(scope=scope).get("cookie"))
        token = set_ui_lang(lang)
        try:
            await self.app(scope, receive, send)
        finally:
            reset_ui_lang(token)


def set_lang_cookie(response: Response, lang: str) -> None:
    response.set_cookie(
        key=LANG_COOKIE_NAME,
        value=normalize_lang(lang),
        max_age=LANG_COOKIE_MAX_AGE,
        httponly=False,  # the offline page reads it to pick a language
        secure=settings.ENVIRONMENT == "production",
        samesite="lax",
        path="/",
    )


def safe_next(raw: str | None) -> str:
    """Only same-site relative paths; anything else falls back to '/' (no open redirect)."""
    path = (raw or "").strip()
    if not path.startswith("/") or path.startswith("//") or "\\" in path or "\n" in path:
        return "/"
    return path


@router.get("/lang/{code}", include_in_schema=False)
async def switch_language(
    code: str,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    current_user: Annotated[AppUser | None, Depends(get_current_user_optional)],
    next: str = "/",
) -> RedirectResponse:
    """Sets the UI language (cookie, plus the signed-in user's `ui_lang`) and redirects back.

    A GET on purpose: it changes only a display preference, needs no CSRF plumbing on pages that
    do not otherwise submit forms, and `next` is restricted to relative paths.
    """
    lang = normalize_lang(code)
    if current_user is not None and current_user.ui_lang != lang:
        current_user.ui_lang = lang
        await db.commit()
    response = RedirectResponse(url=safe_next(next), status_code=303)
    set_lang_cookie(response, lang)
    return response


def speaker_label(speaker: str | None) -> str:
    """Display name for a bubble speaker (catalog `speaker_<id>`), falling back to the raw id."""
    if not speaker:
        return ""
    key = f"speaker_{speaker}"
    return get_message(key) if has_message(key) else speaker


def lang_switch_html(path: str, current: str | None = None) -> Markup:
    """'हिन्दी | English' links that return to `path`; the active language is marked."""
    here = quote(path, safe="/")
    active_lang = normalize_lang(current) if current else get_ui_lang()
    label = escape(get_message("ui_lang_label", lang=active_lang))
    links = []
    for code in SUPPORTED_LANGS:
        name = escape(get_message(f"ui_lang_name_{code}", lang=code))
        cls = (
            ' aria-current="true" class="lang-link active"'
            if code == active_lang
            else ' class="lang-link"'
        )
        links.append(
            f'<a href="/lang/{code}?next={here}" lang="{code}" hreflang="{code}"{cls}>{name}</a>'
        )
    return Markup(  # noqa: S704 - only escaped catalog text and a quoted path
        f'<span class="lang-switch" role="group" aria-label="{label}">{" | ".join(links)}</span>'
    )


@pass_context
def lang_switch(context: Any) -> Markup:
    """Jinja helper: the language switch for the page being rendered."""
    request = context.get("request")
    return lang_switch_html(request.url.path if request is not None else "/")


def register_ui_globals(env: Any) -> None:
    """Make bilingual helpers available to a Jinja environment."""
    env.globals["get_message"] = get_message
    env.globals["speaker_label"] = speaker_label
    env.globals["lang_switch"] = lang_switch
    env.globals["ui_lang"] = get_ui_lang
    env.globals["asset_v"] = sw_build_version
    # Hindi stays Hindi inside the JSON blobs a page embeds (the default escapes every letter to
    # \uXXXX, which doubles their size on the wire); `<`, `>`, `&` and `'` are still escaped
    env.policies["json.dumps_kwargs"] = {"sort_keys": True, "ensure_ascii": False}
