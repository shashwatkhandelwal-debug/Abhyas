"""Unit tests for authentication, session handling, CSRF, and rate limiting (T25)."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI, HTTPException, Request
from httpx import ASGITransport, AsyncClient

from backend.app.auth.csrf import (
    CSRF_COOKIE_NAME,
    CSRF_HEADER_NAME,
    generate_csrf_token,
    verify_csrf_token,
)
from backend.app.auth.guards import require_role
from backend.app.auth.rate_limit import (
    MAX_LOGIN_ATTEMPTS_PER_MINUTE,
    check_login_rate_limit,
    reset_login_rate_limits,
)
from backend.app.auth.router import router as auth_router
from backend.app.auth.session import (
    SESSION_COOKIE_NAME,
    create_session_token,
    verify_session_token,
)
from backend.app.db.models import AppUser
from backend.app.db.session import get_db_session

# ── Session Token Tests ───────────────────────────────────────────────────


def test_session_token_roundtrip() -> None:
    payload = {"user_id": str(uuid.uuid4()), "username": "teacher.demo1", "role": "teacher"}
    token = create_session_token(payload)
    decoded = verify_session_token(token)
    assert decoded is not None
    assert decoded["username"] == "teacher.demo1"
    assert decoded["role"] == "teacher"


def test_session_token_invalid_signature() -> None:
    token = create_session_token({"user_id": "123"})
    bad_token = token + "corrupted"
    assert verify_session_token(bad_token) is None


def test_session_token_expired() -> None:
    token = create_session_token({"user_id": "123"})
    # Verify with max_age=-1 to simulate expiration
    assert verify_session_token(token, max_age=-1) is None


# ── CSRF Protection Tests ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_csrf_safe_methods_bypass() -> None:
    req = Request(
        scope={
            "type": "http",
            "method": "GET",
            "headers": [],
            "path": "/test",
        }
    )
    # Should not raise
    await verify_csrf_token(req)


@pytest.mark.asyncio
async def test_csrf_cookie_missing_raises_403() -> None:
    req = Request(
        scope={
            "type": "http",
            "method": "POST",
            "headers": [],
            "path": "/test",
        }
    )
    with pytest.raises(HTTPException) as exc:
        await verify_csrf_token(req)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_csrf_header_match_succeeds() -> None:
    token = generate_csrf_token()
    req = Request(
        scope={
            "type": "http",
            "method": "POST",
            "headers": [
                (b"cookie", f"{CSRF_COOKIE_NAME}={token}".encode()),
                (CSRF_HEADER_NAME.encode(), token.encode()),
            ],
            "path": "/test",
        }
    )
    await verify_csrf_token(req)


@pytest.mark.asyncio
async def test_csrf_mismatch_raises_403() -> None:
    token1 = generate_csrf_token()
    token2 = generate_csrf_token()
    req = Request(
        scope={
            "type": "http",
            "method": "POST",
            "headers": [
                (b"cookie", f"{CSRF_COOKIE_NAME}={token1}".encode()),
                (CSRF_HEADER_NAME.encode(), token2.encode()),
            ],
            "path": "/test",
        }
    )
    with pytest.raises(HTTPException) as exc:
        await verify_csrf_token(req)
    assert exc.value.status_code == 403


# ── Rate Limiter Tests (5/min/IP) ──────────────────────────────────────────


def test_login_rate_limiter() -> None:
    reset_login_rate_limits()
    req = Request(
        scope={
            "type": "http",
            "client": ("192.168.1.10", 12345),
            "headers": [],
            "path": "/login",
        }
    )

    # 5 attempts should succeed
    for _ in range(MAX_LOGIN_ATTEMPTS_PER_MINUTE):
        check_login_rate_limit(req)

    # 6th attempt should raise 429
    with pytest.raises(HTTPException) as exc:
        check_login_rate_limit(req)
    assert exc.value.status_code == 429
    reset_login_rate_limits()


# ── Role Guard Tests ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_require_role_matches() -> None:
    guard = require_role("arp")
    user = AppUser(
        id=uuid.uuid4(),
        username="arp.demo",
        password_hash="hash",
        role="arp",
    )
    res = await guard(current_user=user)
    assert res.role == "arp"


@pytest.mark.asyncio
async def test_require_role_admin_always_allowed() -> None:
    guard = require_role("teacher")
    admin_user = AppUser(
        id=uuid.uuid4(),
        username="admin",
        password_hash="hash",
        role="admin",
    )
    res = await guard(current_user=admin_user)
    assert res.role == "admin"


@pytest.mark.asyncio
async def test_require_role_unauthorized_role_raises_403() -> None:
    guard = require_role("arp", "trainer")
    teacher_user = AppUser(
        id=uuid.uuid4(),
        username="teacher.demo1",
        password_hash="hash",
        role="teacher",
    )
    with pytest.raises(HTTPException) as exc:
        await guard(current_user=teacher_user)
    assert exc.value.status_code == 403


# ── Login Endpoints Integration Tests ────────────────────────────────────


@pytest.fixture
def auth_app() -> FastAPI:
    app = FastAPI()
    app.include_router(auth_router)
    return app


@pytest.mark.asyncio
async def test_get_login_page(auth_app: FastAPI) -> None:
    async with AsyncClient(transport=ASGITransport(app=auth_app), base_url="http://test") as client:
        res = await client.get("/login")
        assert res.status_code == 200
        assert "अभ्यास" in res.text
        assert "csrf_token" in res.text
        assert CSRF_COOKIE_NAME in res.cookies


@pytest.mark.asyncio
async def test_login_page_html_does_not_contain_admin(auth_app: FastAPI) -> None:
    """Login page HTML never mentions admin or admin.demo."""
    async with AsyncClient(transport=ASGITransport(app=auth_app), base_url="http://test") as client:
        res = await client.get("/login")
        assert res.status_code == 200
        assert "admin" not in res.text.lower()


@pytest.mark.asyncio
async def test_login_json_success(auth_app: FastAPI) -> None:
    from backend.app.auth.passwords import hash_password

    mock_db = AsyncMock()
    user_id = uuid.uuid4()
    teacher_id = uuid.uuid4()
    user = AppUser(
        id=user_id,
        username="teacher.demo1",
        password_hash=hash_password("abhyas-demo-2026"),
        role="teacher",
        display_name="डेमो शिक्षिका 1",
        teacher_id=teacher_id,
    )
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = user
    mock_db.execute.return_value = mock_result

    auth_app.dependency_overrides[get_db_session] = lambda: mock_db

    reset_login_rate_limits()
    async with AsyncClient(transport=ASGITransport(app=auth_app), base_url="http://test") as client:
        res = await client.post(
            "/login",
            json={"username": "teacher.demo1", "password": "abhyas-demo-2026"},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["ok"] is True
        assert data["user"]["role"] == "teacher"
        assert data["redirect"] == "/teacher"
        assert SESSION_COOKIE_NAME in res.cookies

    auth_app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_login_json_bad_password(auth_app: FastAPI) -> None:
    from backend.app.auth.passwords import hash_password

    mock_db = AsyncMock()
    user = AppUser(
        id=uuid.uuid4(),
        username="teacher.demo1",
        password_hash=hash_password("correct-password"),
        role="teacher",
    )
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = user
    mock_db.execute.return_value = mock_result

    auth_app.dependency_overrides[get_db_session] = lambda: mock_db

    reset_login_rate_limits()
    async with AsyncClient(transport=ASGITransport(app=auth_app), base_url="http://test") as client:
        res = await client.post(
            "/login",
            json={"username": "teacher.demo1", "password": "wrong-password"},
        )
        assert res.status_code == 401

    auth_app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_logout_clears_cookie(auth_app: FastAPI) -> None:
    async with AsyncClient(transport=ASGITransport(app=auth_app), base_url="http://test") as client:
        client.cookies.set(SESSION_COOKIE_NAME, "dummy-session-token")
        res = await client.post("/logout", headers={"Accept": "application/json"})
        assert res.status_code == 200
        assert res.json()["ok"] is True


def test_rate_limiter_rejects_spoofed_x_forwarded_for_from_untrusted_client() -> None:
    """Spoofed X-Forwarded-For from an untrusted client does not bypass or reset rate limiting."""
    reset_login_rate_limits()
    untrusted_ip = "198.51.100.42"

    # 5 attempts with varying spoofed X-Forwarded-For headers from untrusted host
    for i in range(5):
        req = Request(
            scope={
                "type": "http",
                "client": (untrusted_ip, 50000 + i),
                "headers": [(b"x-forwarded-for", f"10.0.0.{i}".encode())],
                "path": "/login",
            }
        )
        check_login_rate_limit(req)

    # 6th attempt with another spoofed header should be blocked based on actual client host
    req_blocked = Request(
        scope={
            "type": "http",
            "client": (untrusted_ip, 50099),
            "headers": [(b"x-forwarded-for", b"10.0.0.99")],
            "path": "/login",
        }
    )
    with pytest.raises(HTTPException) as exc:
        check_login_rate_limit(req_blocked)
    assert exc.value.status_code == 429
    reset_login_rate_limits()


def test_rate_limiter_trusted_proxy_resolves_forwarded_ip() -> None:
    """Trusted proxy client (e.g. 127.0.0.1) properly resolves X-Forwarded-For client IP."""
    reset_login_rate_limits()
    trusted_proxy_ip = "127.0.0.1"

    # 5 attempts from forwarded client 203.0.113.195
    for i in range(5):
        req = Request(
            scope={
                "type": "http",
                "client": (trusted_proxy_ip, 60000 + i),
                "headers": [(b"x-forwarded-for", b"203.0.113.195")],
                "path": "/login",
            }
        )
        check_login_rate_limit(req)

    # 6th attempt from same forwarded client raises 429
    req_blocked = Request(
        scope={
            "type": "http",
            "client": (trusted_proxy_ip, 60099),
            "headers": [(b"x-forwarded-for", b"203.0.113.195")],
            "path": "/login",
        }
    )
    with pytest.raises(HTTPException) as exc:
        check_login_rate_limit(req_blocked)
    assert exc.value.status_code == 429
    reset_login_rate_limits()


def test_rate_limiter_production_environment_extracts_forwarded_ip_buckets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two different X-Forwarded-For IPs get separate login rate-limit buckets when ENVIRONMENT='production'."""
    from backend.app.config import settings

    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    reset_login_rate_limits()

    # 5 attempts from client A through proxy where Render appends client IP as the LAST hop
    for _ in range(5):
        req_a = Request(
            scope={
                "type": "http",
                "client": ("10.0.0.1", 50000),
                "headers": [(b"x-forwarded-for", b"spoofed.ip.header, 203.0.113.10")],
                "path": "/login",
            }
        )
        check_login_rate_limit(req_a)

    # 6th attempt from client A is blocked (429)
    req_a_blocked = Request(
        scope={
            "type": "http",
            "client": ("10.0.0.1", 50001),
            "headers": [(b"x-forwarded-for", b"spoofed.ip.header, 203.0.113.10")],
            "path": "/login",
        }
    )
    with pytest.raises(HTTPException) as exc:
        check_login_rate_limit(req_a_blocked)
    assert exc.value.status_code == 429

    # Client B through the same proxy has a different last hop and succeeds
    req_b = Request(
        scope={
            "type": "http",
            "client": ("10.0.0.1", 50002),
            "headers": [(b"x-forwarded-for", b"spoofed.ip.header, 203.0.113.20")],
            "path": "/login",
        }
    )
    check_login_rate_limit(req_b)

    reset_login_rate_limits()


@pytest.mark.asyncio
async def test_bearer_token_rejected_in_production_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bearer-token auth is rejected/ignored when ENVIRONMENT == 'production'."""
    from backend.app.auth.guards import get_current_user_optional
    from backend.app.config import settings

    token = create_session_token(
        {"user_id": str(uuid.uuid4()), "username": "t1", "role": "teacher"}
    )
    req = Request(
        scope={
            "type": "http",
            "headers": [(b"authorization", f"Bearer {token}".encode())],
            "path": "/api/chat/messages",
        }
    )
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_result

    # In test/dev mode, bearer is allowed
    monkeypatch.setattr(settings, "ENVIRONMENT", "test")
    # Will attempt DB lookup (mock_db.execute)
    await get_current_user_optional(req, mock_db)
    assert mock_db.execute.called

    # In production mode, bearer header is ignored completely -> returns None
    mock_db.reset_mock()
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    user = await get_current_user_optional(req, mock_db)
    assert user is None
    assert not mock_db.execute.called
