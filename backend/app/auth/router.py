"""Authentication routes: login, logout, and user profile (spec/07 §7.4, spec/09 §9.7)."""

import html
import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.auth.csrf import (
    CSRF_COOKIE_NAME,
    generate_csrf_token,
    set_csrf_cookie,
    verify_csrf_token,
)
from backend.app.auth.guards import get_current_user, get_current_user_optional
from backend.app.auth.passwords import verify_password
from backend.app.auth.rate_limit import check_login_rate_limit
from backend.app.auth.session import (
    clear_session_cookie,
    create_session_token,
    set_session_cookie,
)
from backend.app.config import settings
from backend.app.core.messages import get_message, get_ui_lang, normalize_lang
from backend.app.db.models import AppUser
from backend.app.db.session import get_db_session
from backend.app.web.ui_lang import lang_switch_html, set_lang_cookie

logger = logging.getLogger("abhyas.auth")

router = APIRouter(tags=["Authentication"])


class LoginRequest(BaseModel):
    username: str
    password: str


ROLE_HOME_PATHS: dict[str, str] = {
    "teacher": "/teacher",
    "arp": "/arp",
    "trainer": "/trainer",
    "coach": "/review",
    "admin": "/admin",
}


def _render_login_page(
    csrf_token: str, error_message: str | None = None, lang: str | None = None
) -> str:
    """Renders the accessible, responsive login page (Hindi default, English on request)."""
    code = normalize_lang(lang) if lang else get_ui_lang()

    def m(key: str, **kwargs: Any) -> str:
        return get_message(key, lang=code, **kwargs)

    error_html = (
        f'<div class="error-banner" role="alert">{html.escape(error_message)}</div>'
        if error_message
        else ""
    )
    demo_creds_html = ""
    if settings.DEMO_MODE:
        demo_title = html.escape(m("ui_login_demo_title", password="@@PW@@")).replace(
            "@@PW@@", f"<code>{html.escape(settings.DEMO_PASSWORD)}</code>"
        )
        demo_creds_html = f"""
        <div class="demo-card">
            <h3>{demo_title}</h3>
            <div class="demo-chips">
                <button type="button" onclick="fillCreds('teacher.demo1')">{html.escape(m("ui_login_demo_teacher_new"))}</button>
                <button type="button" onclick="fillCreds('teacher.demo2')">{html.escape(m("ui_login_demo_teacher_practiced"))}</button>
                <button type="button" onclick="fillCreds('arp.demo')">{html.escape(m("ui_login_demo_arp"))}</button>
                <button type="button" onclick="fillCreds('trainer.demo')">{html.escape(m("ui_login_demo_trainer"))}</button>
                <button type="button" onclick="fillCreds('coach.demo')">{html.escape(m("ui_login_demo_coach"))}</button>
            </div>
        </div>
        """
    switch_html = lang_switch_html("/login", code)

    return f"""<!DOCTYPE html>
<html lang="{code}">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{html.escape(m("ui_login_page_title"))}</title>
    <style>
        :root {{
            --bg: #FAF7F2;
            --surface: #FFFFFF;
            --ink: #1F2421;
            --muted: #5E6662;
            --brand: #1F6F5C;
            --brand-ink: #FFFFFF;
            --accent: #E0A100;
            --danger: #B3261E;
        }}
        body {{
            margin: 0;
            padding: 1.5rem;
            background: var(--bg);
            color: var(--ink);
            font-family: "Noto Sans Devanagari", "Mukta", system-ui, sans-serif;
            font-size: 17px;
            line-height: 1.6;
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            box-sizing: border-box;
        }}
        .login-box {{
            background: var(--surface);
            border-radius: 12px;
            box-shadow: 0 4px 20px rgba(0,0,0,0.08);
            width: 100%;
            max-width: 440px;
            padding: 2rem;
            box-sizing: border-box;
        }}
        .brand-header {{
            text-align: center;
            margin-bottom: 1.5rem;
        }}
        .brand-title {{
            font-size: 2rem;
            font-weight: 700;
            color: var(--brand);
            margin: 0;
        }}
        .brand-subtitle {{
            color: var(--muted);
            font-size: 0.95rem;
            margin-top: 0.25rem;
        }}
        .form-group {{
            margin-bottom: 1.25rem;
        }}
        label {{
            display: block;
            margin-bottom: 0.5rem;
            font-weight: 600;
        }}
        input[type="text"], input[type="password"] {{
            width: 100%;
            padding: 0.75rem 1rem;
            border: 1px solid #D0D7D3;
            border-radius: 8px;
            font-size: 1rem;
            box-sizing: border-box;
            min-height: 48px;
        }}
        input:focus {{
            outline: 2px solid var(--brand);
            border-color: var(--brand);
        }}
        .btn-submit {{
            width: 100%;
            background: var(--brand);
            color: var(--brand-ink);
            border: none;
            border-radius: 8px;
            padding: 0.85rem;
            font-size: 1.1rem;
            font-weight: 600;
            cursor: pointer;
            min-height: 48px;
            margin-top: 0.5rem;
        }}
        .btn-submit:hover {{
            background: #175446;
        }}
        .error-banner {{
            background: #FDF2F2;
            color: var(--danger);
            border: 1px solid var(--danger);
            border-radius: 8px;
            padding: 0.75rem 1rem;
            margin-bottom: 1.25rem;
            font-size: 0.95rem;
        }}
        .lang-row {{ margin: 0.5rem 0 0; font-size: 0.9rem; }}
        .lang-link {{ color: var(--brand); text-decoration: none; padding: 0.4rem 0.5rem; display: inline-block; }}
        .lang-link.active {{ font-weight: 700; text-decoration: underline; }}
        .demo-card {{
            margin-top: 1.75rem;
            padding-top: 1.25rem;
            border-top: 1px dashed #D0D7D3;
        }}
        .demo-card h3 {{
            margin: 0 0 0.75rem 0;
            font-size: 0.95rem;
            color: var(--muted);
        }}
        .demo-chips {{
            display: flex;
            flex-wrap: wrap;
            gap: 0.5rem;
        }}
        .demo-chips button {{
            background: #EDEAE4;
            border: 1px solid #D8D4CC;
            border-radius: 20px;
            padding: 0.4rem 0.8rem;
            font-size: 0.85rem;
            cursor: pointer;
            color: var(--ink);
        }}
        .demo-chips button:hover {{
            background: #DFDBD3;
        }}
    </style>
</head>
<body>
    <main class="login-box">
        <header class="brand-header">
            <h1 class="brand-title">{html.escape(m("ui_app_name"))}</h1>
            <p class="brand-subtitle">{html.escape(m("ui_login_subtitle"))}</p>
        <p class="lang-row">{switch_html}</p>
        </header>

        {error_html}

        <form method="POST" action="/login">
            <input type="hidden" name="csrf_token" value="{csrf_token}">
            <input type="hidden" name="ui_lang" value="{code}">

            <div class="form-group">
                <label for="username">{html.escape(m("ui_login_username"))}</label>
                <input type="text" id="username" name="username" required autocomplete="username" autofocus>
            </div>

            <div class="form-group">
                <label for="password">{html.escape(m("ui_login_password"))}</label>
                <input type="password" id="password" name="password" required autocomplete="current-password">
            </div>

            <button type="submit" class="btn-submit">{html.escape(m("ui_login_submit"))}</button>
        </form>

        {demo_creds_html}
    </main>
    <script>
        function fillCreds(username) {{
            document.getElementById('username').value = username;
            document.getElementById('password').value = "{settings.DEMO_PASSWORD}";
        }}
    </script>
    <script src="/static/ack.js" defer data-opening="{html.escape(m("ui_nav_opening"))}" data-waking="{html.escape(m("ui_nav_waking"))}"></script>
</body>
</html>"""


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request) -> Response:
    """Renders login page and ensures CSRF cookie is present."""
    csrf_token = request.cookies.get(CSRF_COOKIE_NAME)
    token_to_set: str | None = None
    if not csrf_token:
        csrf_token = generate_csrf_token()
        token_to_set = csrf_token

    html_content = _render_login_page(csrf_token)
    response = HTMLResponse(content=html_content)
    if token_to_set:
        set_csrf_cookie(response, token_to_set)
    return response


@router.post("/login")
async def login(
    request: Request,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    username: Annotated[str | None, Form()] = None,
    password: Annotated[str | None, Form()] = None,
    csrf_token: Annotated[str | None, Form()] = None,
    ui_lang: Annotated[str | None, Form()] = None,
) -> Response:
    """Authenticates user with rate limiting (5/min/IP), CSRF verification, and signed session cookie."""
    # 1. Rate limiting: 5/min/IP (§7.4)
    check_login_rate_limit(request)

    # 2. Check content-type: support both Form and JSON
    user_val: str | None = username
    pass_val: str | None = password
    is_json = False

    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        is_json = True
        try:
            body = await request.json()
            user_val = body.get("username")
            pass_val = body.get("password")
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=get_message("ui_login_api_bad_json"),
            ) from None
    else:
        # Verify CSRF on form submissions
        await verify_csrf_token(request)

    if not user_val or not pass_val:
        if is_json:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=get_message("ui_login_api_missing"),
            )
        token = request.cookies.get(CSRF_COOKIE_NAME) or generate_csrf_token()
        resp = HTMLResponse(
            _render_login_page(token, get_message("ui_login_error_missing")),
            status_code=400,
        )
        set_csrf_cookie(resp, token)
        return resp

    # 3. Lookup user in database
    stmt = select(AppUser).where(AppUser.username == user_val.strip())
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user or not verify_password(pass_val, user.password_hash):
        if is_json:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=get_message("ui_login_api_invalid"),
            )
        token = request.cookies.get(CSRF_COOKIE_NAME) or generate_csrf_token()
        resp = HTMLResponse(
            _render_login_page(token, get_message("ui_login_error_invalid")),
            status_code=401,
        )
        set_csrf_cookie(resp, token)
        return resp

    # 4. Create session token
    session_payload: dict[str, Any] = {
        "user_id": str(user.id),
        "username": user.username,
        "role": user.role,
        "teacher_id": str(user.teacher_id) if user.teacher_id else None,
        "cluster_id": user.cluster_id,
        "district": user.district,
    }
    session_token = create_session_token(session_payload)
    redirect_path = ROLE_HOME_PATHS.get(user.role, "/teacher")

    # UI language: the choice made on the login page wins; otherwise the user's saved preference,
    # then whatever this browser already had. Saved back so it follows the user across devices.
    chosen_lang = normalize_lang(ui_lang or user.ui_lang or get_ui_lang())
    if user.ui_lang != chosen_lang:
        user.ui_lang = chosen_lang
        await db.commit()

    if is_json:
        json_resp = JSONResponse(
            content={
                "ok": True,
                "user": {
                    "id": str(user.id),
                    "username": user.username,
                    "role": user.role,
                    "display_name": user.display_name,
                    "teacher_id": str(user.teacher_id) if user.teacher_id else None,
                },
                "redirect": redirect_path,
            }
        )
        set_session_cookie(json_resp, session_token)
        set_lang_cookie(json_resp, chosen_lang)
        return json_resp

    # Redirect to role home (§9.7)
    redir_resp = RedirectResponse(url=redirect_path, status_code=status.HTTP_303_SEE_OTHER)
    set_session_cookie(redir_resp, session_token)
    set_lang_cookie(redir_resp, chosen_lang)
    return redir_resp


async def _reset_demo_teacher_on_logout(db: AsyncSession, user: AppUser | None) -> None:
    """Resets a shared demo teacher login to the seeded state. Never blocks the logout."""
    if user is None or not user.is_demo or user.role != "teacher":
        return
    from backend.app.db.seed import reset_demo_teacher

    try:
        async with db.begin_nested():
            await reset_demo_teacher(db, user.username)
    except Exception:
        logger.exception("demo_reset_failed username=%s", user.username)


@router.post("/logout")
@router.get("/logout")
async def logout(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> Response:
    """Logs user out by clearing session cookie (§9.7); shared demo teachers are reset."""
    try:
        user = await get_current_user_optional(request, db)
    except Exception:
        logger.exception("logout_user_lookup_failed")
        user = None
    await _reset_demo_teacher_on_logout(db, user)

    accept = request.headers.get("accept", "")
    if "application/json" in accept and "text/html" not in accept:
        json_resp = JSONResponse(content={"ok": True, "redirect": "/login"})
        clear_session_cookie(json_resp)
        return json_resp

    redir_resp = RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    clear_session_cookie(redir_resp)
    return redir_resp


@router.get("/api/auth/me")
async def get_me(current_user: Annotated[AppUser, Depends(get_current_user)]) -> dict[str, Any]:
    """Returns profile for currently authenticated user."""
    return {
        "id": str(current_user.id),
        "username": current_user.username,
        "role": current_user.role,
        "display_name": current_user.display_name,
        "teacher_id": str(current_user.teacher_id) if current_user.teacher_id else None,
        "cluster_id": current_user.cluster_id,
        "district": current_user.district,
        "is_demo": current_user.is_demo,
    }
