"""Unit tests for ARP Digest router, role guards, CSRF, and template rendering (spec/09 §9.3, T32)."""

import unicodedata
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.auth.guards import get_current_user
from backend.app.db.models import AppUser, Teacher
from backend.app.db.session import get_db_session
from backend.app.web.arp import router as arp_router


@pytest.fixture
def arp_app() -> FastAPI:
    app = FastAPI()
    app.include_router(arp_router)
    return app


@pytest.fixture
def arp_user() -> AppUser:
    return AppUser(
        id=uuid.uuid4(),
        username="arp.demo",
        role="arp",
        cluster_id="KNP-C01",
        display_name="ए.आर.पी. कल्याणपुर",
        password_hash="hash",
    )


@pytest.fixture
def teacher_user() -> AppUser:
    return AppUser(
        id=uuid.uuid4(),
        username="teacher.demo1",
        role="teacher",
        teacher_id=uuid.uuid4(),
        password_hash="hash",
    )


@pytest.mark.asyncio
async def test_arp_route_requires_arp_or_admin_role(
    arp_app: FastAPI,
    teacher_user: AppUser,
) -> None:
    """A user with role 'teacher' must be rejected with 403 Forbidden on /arp."""
    arp_app.dependency_overrides[get_current_user] = lambda: teacher_user
    arp_app.dependency_overrides[get_db_session] = lambda: AsyncMock(spec=AsyncSession)

    transport = ASGITransport(app=arp_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        res = await client.get("/arp")
        assert res.status_code == 403
        assert "Role required" in res.json()["detail"]


@pytest.mark.asyncio
async def test_arp_dashboard_renders_clean_nfc_html(
    arp_app: FastAPI,
    arp_user: AppUser,
) -> None:
    """Verifies that /arp renders template properly and content is NFC-normalized."""
    mock_db = AsyncMock(spec=AsyncSession)
    arp_app.dependency_overrides[get_current_user] = lambda: arp_user
    arp_app.dependency_overrides[get_db_session] = lambda: mock_db

    # Mock DB query results for build_arp_digest
    cluster_mock = MagicMock()
    cluster_mock.name = "कल्याणपुर क्लस्टर 1"
    mock_db.get.return_value = cluster_mock

    # Scalars mock returning 1 consenting teacher and 1 non-consenting
    t_consent = Teacher(
        id=uuid.uuid4(),
        name="सुनीता शर्मा",
        school_id="प्रा.वि. कल्यानपुर",
        cluster_id="KNP-C01",
        consent_share_scores=True,
    )
    t_non_consent = Teacher(
        id=uuid.uuid4(),
        name="गुप्त शिक्षिका",
        school_id="प्रा.वि. गुप्त",
        cluster_id="KNP-C01",
        consent_share_scores=False,
    )

    # Mock execute/scalars
    teachers_scalars = MagicMock()
    teachers_scalars.all.return_value = [t_consent, t_non_consent]

    empty_scalars = MagicMock()
    empty_scalars.all.return_value = []

    empty_exec = MagicMock()
    empty_exec.all.return_value = []

    mock_db.scalars.side_effect = [
        teachers_scalars,  # teachers query
        empty_scalars,  # session states query
        empty_scalars,  # rehearsal scores query
        empty_scalars,  # questions query
    ]
    mock_db.execute.side_effect = [
        empty_exec,  # evidence query
    ]

    transport = ASGITransport(app=arp_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        res = await client.get("/arp")
        assert res.status_code == 200
        html = res.text

        # Verify NFC normalization
        assert html == unicodedata.normalize("NFC", html)

        # Consenting teacher visible
        assert "सुनीता शर्मा" in html
        # Non-consenting teacher name NEVER visible
        assert "गुप्त शिक्षिका" not in html
        # Aggregate row visible
        assert "स्कोर साझा नहीं" in html


@pytest.mark.asyncio
async def test_arp_post_without_csrf_fails_forbidden(
    arp_app: FastAPI,
    arp_user: AppUser,
) -> None:
    """POST /arp/observation and /arp/answer without CSRF token must return 403 Forbidden."""
    arp_app.dependency_overrides[get_current_user] = lambda: arp_user
    arp_app.dependency_overrides[get_db_session] = lambda: AsyncMock(spec=AsyncSession)

    transport = ASGITransport(app=arp_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # Observation without CSRF
        res1 = await client.post(
            "/arp/observation",
            data={"teacher_id": str(uuid.uuid4()), "move_id": "TEST_MOVE"},
        )
        assert res1.status_code == 403

        # Answer without CSRF
        res2 = await client.post(
            "/arp/answer",
            data={"question_id": str(uuid.uuid4()), "answer_hi": "उत्तर"},
        )
        assert res2.status_code == 403
