"""Unit tests for operations admin dashboard (/admin) (spec/09 §9.6, spec/14 T35)."""

import uuid
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.auth.csrf import (
    CSRF_COOKIE_NAME,
    generate_csrf_token,
)
from backend.app.auth.guards import get_current_user
from backend.app.db.models import AppUser, Teacher
from backend.app.db.session import get_db_session
from backend.app.jobs.tick import FastForwardResult, JobOutcome
from backend.app.main import app
from backend.app.web.admin import calc_percentile

# ── Percentile Calculation Tests ──────────────────────────────────────────────


def test_calc_percentile_empty() -> None:
    assert calc_percentile([], 50) == 0
    assert calc_percentile([], 95) == 0


def test_calc_percentile_single() -> None:
    assert calc_percentile([42], 50) == 42
    assert calc_percentile([42], 95) == 42


def test_calc_percentile_multiple() -> None:
    values = [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
    assert calc_percentile(values, 50) in (50, 55, 60)
    assert calc_percentile(values, 95) >= 90


# ── Route Auth & Guard Tests ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_admin_dashboard_forbidden_for_teacher() -> None:
    """Verifies that non-admin roles (e.g. teacher) cannot access /admin."""
    teacher_user = AppUser(
        id=uuid.uuid4(),
        username="teacher.test",
        role="teacher",
        display_name="परीक्षण शिक्षिका",
    )

    async def override_teacher() -> AppUser:
        return teacher_user

    app.dependency_overrides[get_current_user] = override_teacher

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        res = await client.get("/admin")
        assert res.status_code == 403

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_admin_dashboard_renders_for_admin() -> None:
    """Verifies that admin user accesses /admin and gets all dashboard cards."""
    admin_user = AppUser(
        id=uuid.uuid4(),
        username="admin",
        role="admin",
        display_name="मुख्य एडमिन",
    )

    mock_db = AsyncMock(spec=AsyncSession)
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_result.scalar.return_value = 0
    mock_result.scalars.return_value.all.return_value = []
    mock_result.all.return_value = []
    mock_db.execute = AsyncMock(return_value=mock_result)

    async def override_admin() -> AppUser:
        return admin_user

    async def override_db() -> AsyncIterator[AsyncSession]:
        yield mock_db

    app.dependency_overrides[get_current_user] = override_admin
    app.dependency_overrides[get_db_session] = override_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        res = await client.get("/admin")
        assert res.status_code == 200
        html = res.text
        assert "अभ्यास एडमिन डैशबोर्ड" in html
        assert "ENVIRONMENT" in html
        assert "विलंबता" in html
        assert "टर्न गतिविधि" in html
        assert "गार्ड प्रदर्शन" in html
        assert "डेमो नियंत्रण" in html

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_admin_reset_demo_csrf_check() -> None:
    """Verifies that POST /admin/reset-demo requires valid CSRF."""
    admin_user = AppUser(
        id=uuid.uuid4(),
        username="admin",
        role="admin",
    )

    app.dependency_overrides[get_current_user] = lambda: admin_user

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # No CSRF cookie or form token
        res = await client.post("/admin/reset-demo")
        assert res.status_code == 403

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_admin_reset_demo_success() -> None:
    """Verifies POST /admin/reset-demo with CSRF token triggers reset and redirects."""
    admin_user = AppUser(
        id=uuid.uuid4(),
        username="admin",
        role="admin",
    )

    app.dependency_overrides[get_current_user] = lambda: admin_user

    csrf = generate_csrf_token()
    transport = ASGITransport(app=app)

    with patch("backend.app.web.admin.reset_demo_data", new_callable=AsyncMock) as mock_reset:
        mock_reset.return_value = {"reset_teachers": 3}
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            client.cookies.set(CSRF_COOKIE_NAME, csrf)
            res = await client.post(
                "/admin/reset-demo",
                data={"csrf_token": csrf},
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                follow_redirects=False,
            )
            assert res.status_code == 303
            assert "/admin?msg=reset_ok" in res.headers["location"]
            mock_reset.assert_awaited_once()

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_admin_fast_forward_success() -> None:
    """Verifies POST /admin/fast-forward calls fast_forward_teacher and redirects for demo teachers."""
    admin_user = AppUser(
        id=uuid.uuid4(),
        username="admin",
        role="admin",
    )
    teacher_id = uuid.uuid4()
    demo_teacher = Teacher(
        id=teacher_id,
        name="सुनीता देवी",
        is_demo=True,
    )

    mock_db = AsyncMock(spec=AsyncSession)
    mock_db.get = AsyncMock(return_value=demo_teacher)

    async def override_db() -> AsyncIterator[AsyncSession]:
        yield mock_db

    app.dependency_overrides[get_current_user] = lambda: admin_user
    app.dependency_overrides[get_db_session] = override_db

    csrf = generate_csrf_token()
    transport = ASGITransport(app=app)

    with patch("backend.app.web.admin.fast_forward_teacher", new_callable=AsyncMock) as mock_ff:
        mock_ff.return_value = FastForwardResult(
            advanced=2,
            outcomes=[JobOutcome(job_id=uuid.uuid4(), kind="prompt_rehearse", status="done")],
        )
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            client.cookies.set(CSRF_COOKIE_NAME, csrf)
            res = await client.post(
                "/admin/fast-forward",
                data={"csrf_token": csrf, "teacher_id": str(teacher_id)},
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                follow_redirects=False,
            )
            assert res.status_code == 303
            assert "/admin?msg=ff_ok&advanced=2" in res.headers["location"]
            mock_ff.assert_awaited_once_with(teacher_id)

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_admin_fast_forward_rejects_non_demo_teacher() -> None:
    """Verifies POST /admin/fast-forward rejects non-demo teachers with 400."""
    admin_user = AppUser(
        id=uuid.uuid4(),
        username="admin",
        role="admin",
    )
    teacher_id = uuid.uuid4()
    real_teacher = Teacher(
        id=teacher_id,
        name="असली शिक्षक",
        is_demo=False,
    )

    mock_db = AsyncMock(spec=AsyncSession)
    mock_db.get = AsyncMock(return_value=real_teacher)

    async def override_db() -> AsyncIterator[AsyncSession]:
        yield mock_db

    app.dependency_overrides[get_current_user] = lambda: admin_user
    app.dependency_overrides[get_db_session] = override_db

    csrf = generate_csrf_token()
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        client.cookies.set(CSRF_COOKIE_NAME, csrf)
        res = await client.post(
            "/admin/fast-forward",
            data={"csrf_token": csrf, "teacher_id": str(teacher_id)},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            follow_redirects=False,
        )
        assert res.status_code == 400
        assert "Cannot fast-forward a non-demo teacher" in res.text

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_admin_fast_forward_teacher_not_found() -> None:
    """Verifies POST /admin/fast-forward returns 404 if teacher does not exist."""
    admin_user = AppUser(
        id=uuid.uuid4(),
        username="admin",
        role="admin",
    )
    mock_db = AsyncMock(spec=AsyncSession)
    mock_db.get = AsyncMock(return_value=None)

    async def override_db() -> AsyncIterator[AsyncSession]:
        yield mock_db

    app.dependency_overrides[get_current_user] = lambda: admin_user
    app.dependency_overrides[get_db_session] = override_db

    csrf = generate_csrf_token()
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        client.cookies.set(CSRF_COOKIE_NAME, csrf)
        res = await client.post(
            "/admin/fast-forward",
            data={"csrf_token": csrf, "teacher_id": str(uuid.uuid4())},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            follow_redirects=False,
        )
        assert res.status_code == 404

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_admin_fast_forward_invalid_uuid() -> None:
    """Verifies POST /admin/fast-forward with bad UUID redirects to error."""
    admin_user = AppUser(
        id=uuid.uuid4(),
        username="admin",
        role="admin",
    )

    app.dependency_overrides[get_current_user] = lambda: admin_user

    csrf = generate_csrf_token()
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        client.cookies.set(CSRF_COOKIE_NAME, csrf)
        res = await client.post(
            "/admin/fast-forward",
            data={"csrf_token": csrf, "teacher_id": "not-a-uuid"},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            follow_redirects=False,
        )
        assert res.status_code == 303
        assert "/admin?msg=error" in res.headers["location"]

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_reset_demo_data_targets_only_seed_teachers() -> None:
    """Verifies reset_demo_data targets SEED_TEACHER_IDS and resets demo1..3 states."""
    from backend.app.db.demo_data import SEED_TEACHER_IDS
    from backend.app.web.admin import reset_demo_data

    mock_db = AsyncMock(spec=AsyncSession)
    mock_exec = MagicMock()
    mock_exec.scalars.return_value.all.return_value = []
    mock_db.execute = AsyncMock(return_value=mock_exec)

    t1 = Teacher(id=SEED_TEACHER_IDS[0], is_demo=True, onboarding_state="DONE")
    t2 = Teacher(id=SEED_TEACHER_IDS[1], is_demo=True, onboarding_state="DONE")
    t3 = Teacher(id=SEED_TEACHER_IDS[2], is_demo=True, onboarding_state="DONE")

    async def fake_get(model: Any, pk: Any) -> Any:
        if pk == SEED_TEACHER_IDS[0]:
            return t1
        elif pk == SEED_TEACHER_IDS[1]:
            return t2
        elif pk == SEED_TEACHER_IDS[2]:
            return t3
        return None

    mock_db.get = AsyncMock(side_effect=fake_get)

    result = await reset_demo_data(mock_db)
    assert result == {"reset_teachers": 3}
    assert t1.onboarding_state == "NEW"
    assert t2.onboarding_state == "COMPLETE"
    assert t3.onboarding_state == "COMPLETE"
    assert mock_db.commit.awaited
