"""CI Smoke Test Suite for Abhyas (spec/12 §12.9, Job 08).

Verifies core health probes and basic end-to-end user flows:
1. Health & Liveness probes (/healthz, /health, /readyz)
2. Authentication entrypoints (GET / -> /login, CSRF generation)
3. Teacher chat & inbound turn flow (login -> /teacher -> /api/chat/text -> /logout)
4. Role-based navigation guards (/arp, /trainer, /review, /admin)
5. Smoke runner script validation

Runs entirely without external secrets, database dependencies, or deployment steps.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from backend.app.auth.session import create_session_token
from backend.app.main import app
from scripts.smoke_test import (
    CSRF_COOKIE_NAME,
    CSRF_HEADER_NAME,
    SESSION_COOKIE_NAME,
    extract_csrf_token,
    run_smoke_test,
)


@pytest.fixture
def mock_teacher_user() -> MagicMock:
    user = MagicMock()
    user.id = uuid.uuid4()
    user.username = "teacher.demo1"
    user.role = "teacher"
    user.display_name = "डेमो शिक्षिका"
    user.teacher_id = uuid.uuid4()
    user.cluster_id = "KNP-C01"
    user.district = "Kanpur Nagar"
    user.is_demo = True
    return user


@pytest.mark.asyncio
async def test_smoke_health_probes() -> None:
    """Smoke test: Liveness, readiness, and detailed health endpoints."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        # 1. Liveness probe /healthz
        res_z = await client.get("/healthz")
        assert res_z.status_code == 200
        data_z = res_z.json()
        assert data_z["status"] == "ok"
        assert "git_sha" in data_z

        # 2. Service health /health
        res_h = await client.get("/health")
        assert res_h.status_code == 200
        data_h = res_h.json()
        assert data_h["status"] == "healthy"
        assert data_h["service"] == "abhyas-backend"

        # 3. Readiness probe /readyz
        with patch("backend.app.main.async_session_factory") as mock_factory:
            mock_session = AsyncMock()
            mock_factory.return_value.__aenter__.return_value = mock_session
            res_r = await client.get("/readyz")
            assert res_r.status_code == 200
            assert res_r.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_smoke_login_entry_and_csrf() -> None:
    """Smoke test: Root redirect and CSRF token generation on login page."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver", follow_redirects=False
    ) as client:
        # Root redirects to /login
        res_root = await client.get("/")
        assert res_root.status_code == 303
        assert res_root.headers["location"] == "/login"

        # /login renders and sets CSRF cookie
        res_login = await client.get("/login")
        assert res_login.status_code == 200
        assert "csrf_token" in res_login.text
        assert CSRF_COOKIE_NAME in res_login.cookies
        token = extract_csrf_token(res_login.text, res_login.cookies)
        assert token is not None
        assert len(token) > 10


@pytest.mark.asyncio
async def test_smoke_teacher_flow_end_to_end(mock_teacher_user: MagicMock) -> None:
    """Smoke test: Login -> access teacher chat -> send turn -> logout."""
    from datetime import UTC, datetime

    from backend.app.auth.guards import get_current_user
    from backend.app.db.session import get_db_session

    token = create_session_token(
        {
            "user_id": str(mock_teacher_user.id),
            "role": "teacher",
            "username": mock_teacher_user.username,
            "display_name": mock_teacher_user.display_name,
            "teacher_id": str(mock_teacher_user.teacher_id),
            "cluster_id": mock_teacher_user.cluster_id,
            "district": mock_teacher_user.district,
            "is_demo": True,
        }
    )

    mock_db = AsyncMock()
    mock_res = MagicMock()
    mock_res.scalars.return_value.all.return_value = []
    mock_res.scalar_one_or_none.return_value = None
    mock_res.scalar.return_value = None
    mock_db.execute.return_value = mock_res

    async def _override_db():
        yield mock_db

    mock_teacher = MagicMock()
    mock_teacher.id = mock_teacher_user.teacher_id
    mock_teacher.start_seen_at = datetime.now(UTC)
    mock_teacher.consent_service = True
    mock_teacher.onboarding_state = "READY"
    mock_teacher.address_form = "female"

    app.dependency_overrides[get_db_session] = _override_db
    app.dependency_overrides[get_current_user] = lambda: mock_teacher_user

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver", follow_redirects=False
        ) as client:
            # Pre-set auth cookie
            client.cookies.set(SESSION_COOKIE_NAME, token)
            client.cookies.set(CSRF_COOKIE_NAME, "test-smoke-csrf-token")

            # 1. GET /teacher
            with patch("backend.app.web.teacher.get_teacher_for_user", return_value=mock_teacher):
                res_t = await client.get("/teacher")
                assert res_t.status_code in (200, 303)

            # 2. POST /api/chat/text
            with patch("backend.app.web.chat_api.verify_csrf_token", return_value=True):
                with patch("backend.app.web.chat_api.process_inbound_web"):
                    mock_db.get.return_value = mock_teacher
                    payload = {
                        "client_msg_id": str(uuid.uuid4()),
                        "text": "नमस्ते रवि, आज हम घटाव सीखेंगे।",
                    }
                    headers = {CSRF_HEADER_NAME: "test-smoke-csrf-token"}
                    res_chat = await client.post("/api/chat/text", json=payload, headers=headers)
                    assert res_chat.status_code in (200, 202)

            # 3. GET /logout
            res_out = await client.get("/logout")
            assert res_out.status_code == 303
            assert res_out.headers["location"] == "/login"
    finally:
        app.dependency_overrides.pop(get_db_session, None)
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_smoke_role_guards_unauthorized() -> None:
    """Smoke test: Protected oversight routes require appropriate role authentication."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver", follow_redirects=False
    ) as client:
        for protected_path in ("/arp", "/trainer", "/review", "/admin"):
            res = await client.get(protected_path)
            # Unauthenticated visitors must be redirected to /login or denied 401/403
            assert res.status_code in (302, 303, 401, 403), f"Route {protected_path} must be protected"


def test_smoke_runner_script_mock_success() -> None:
    """Smoke test: Verifies scripts.smoke_test executes and reports 100% pass on valid client."""
    mock_client = MagicMock()

    # Step 1: /healthz
    r1 = MagicMock()
    r1.status_code = 200
    r1.json.return_value = {"status": "ok", "git_sha": "test-sha"}

    # Step 2: /login
    r2 = MagicMock()
    r2.status_code = 200
    r2.text = '<input type="hidden" name="csrf_token" value="smoke_csrf_12345">'

    # Step 3: POST /login
    r3 = MagicMock()
    r3.status_code = 303
    r3.headers = {"location": "/teacher"}

    # Step 4: POST /api/chat/text
    r4 = MagicMock()
    r4.status_code = 202
    r4.headers = {"content-type": "application/json"}
    r4.json.return_value = {"message_id": "msg_smoke_abc"}

    mock_client.get.side_effect = [r1, r2]
    mock_client.post.side_effect = [r3, r4]
    mock_client.cookies = {
        CSRF_COOKIE_NAME: "smoke_csrf_12345",
        SESSION_COOKIE_NAME: "smoke_session_token_xyz",
    }

    success = run_smoke_test(base_url="http://testserver", client=mock_client)
    assert success is True
