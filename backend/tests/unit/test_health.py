"""Tests for system health, liveness, static assets, and web entrypoints (spec/12, T30)."""

from unittest.mock import MagicMock

import httpx
import pytest
from httpx import AsyncClient

from backend.app.config import settings
from scripts.smoke_test import (
    CSRF_COOKIE_NAME,
    SESSION_COOKIE_NAME,
    extract_csrf_token,
    run_smoke_test,
)


@pytest.mark.asyncio
async def test_health_check(async_client: AsyncClient) -> None:
    """Verifies detailed health check endpoint."""
    response = await async_client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "abhyas-backend"
    assert data["environment"] == settings.ENVIRONMENT


@pytest.mark.asyncio
async def test_healthz_endpoint(async_client: AsyncClient) -> None:
    """Verifies lightweight liveness probe returns status ok and git SHA (§12)."""
    response = await async_client.get("/healthz")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["git_sha"] == settings.GIT_SHA


@pytest.mark.asyncio
async def test_root_redirect(async_client: AsyncClient) -> None:
    """Verifies GET / redirects to /login with status code 303."""
    response = await async_client.get("/", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"


@pytest.mark.asyncio
async def test_login_page_renders(async_client: AsyncClient) -> None:
    """Verifies GET /login serves Hindi login UI and sets CSRF cookie."""
    response = await async_client.get("/login")
    assert response.status_code == 200
    assert "अभ्यास" in response.text
    assert "abhyas_csrf" in response.cookies
    assert "csrf_token" in response.text


@pytest.mark.asyncio
async def test_manifest_json(async_client: AsyncClient) -> None:
    """Verifies GET /manifest.json serves PWA manifest with correct media type."""
    response = await async_client.get("/manifest.json")
    assert response.status_code == 200
    assert "application/manifest+json" in response.headers.get("content-type", "")
    data = response.json()
    assert "अभ्यास" in data.get("name", "")
    assert data.get("start_url") == "/teacher"


@pytest.mark.asyncio
async def test_service_worker(async_client: AsyncClient) -> None:
    """Verifies GET /sw.js serves service worker with Service-Worker-Allowed root header."""
    response = await async_client.get("/sw.js")
    assert response.status_code == 200
    assert "application/javascript" in response.headers.get("content-type", "")
    assert response.headers.get("Service-Worker-Allowed") == "/"
    assert "abhyas-static-v" in response.text


@pytest.mark.asyncio
async def test_static_mounts(async_client: AsyncClient) -> None:
    """Verifies static asset mount at /static serves css and icons."""
    css_resp = await async_client.get("/static/app.css")
    assert css_resp.status_code == 200
    assert "text/css" in css_resp.headers.get("content-type", "")

    icon_resp = await async_client.get("/static/icon-192.svg")
    assert icon_resp.status_code == 200
    assert "image/svg+xml" in icon_resp.headers.get("content-type", "")


def test_extract_csrf_token() -> None:
    """Verifies CSRF token extraction from HTML forms and cookies."""
    html = '<form><input type="hidden" name="csrf_token" value="token_val_123"></form>'
    cookies = httpx.Cookies()
    assert extract_csrf_token(html, cookies) == "token_val_123"

    html_inverted = '<input value="token_val_456" name="csrf_token">'
    assert extract_csrf_token(html_inverted, cookies) == "token_val_456"

    cookies.set(CSRF_COOKIE_NAME, "token_from_cookie")
    assert extract_csrf_token("<div>no form</div>", cookies) == "token_from_cookie"


def test_smoke_test_with_mock_client() -> None:
    """Verifies that run_smoke_test succeeds end-to-end with valid responses."""
    mock_client = MagicMock()

    # Step 1: GET /healthz
    r1 = MagicMock()
    r1.status_code = 200
    r1.json.return_value = {"status": "ok", "git_sha": "test-sha"}

    # Step 2: GET /login
    r2 = MagicMock()
    r2.status_code = 200
    r2.text = '<input type="hidden" name="csrf_token" value="test-csrf">'

    # Step 3: POST /login
    r3 = MagicMock()
    r3.status_code = 303
    r3.headers = {"location": "/teacher"}

    # Step 4: POST /api/chat/text
    r4 = MagicMock()
    r4.status_code = 202
    r4.headers = {"content-type": "application/json"}
    r4.json.return_value = {"message_id": "msg-123"}

    mock_client.get.side_effect = [r1, r2]
    mock_client.post.side_effect = [r3, r4]

    mock_cookies = {
        CSRF_COOKIE_NAME: "test-csrf",
        SESSION_COOKIE_NAME: "test-session",
    }
    mock_client.cookies.get = lambda k: mock_cookies.get(k)

    result = run_smoke_test(base_url="http://testserver", client=mock_client)
    assert result is True
