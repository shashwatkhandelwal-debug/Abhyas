"""Integration tests for operations admin dashboard against real PostgreSQL (spec/09 §9.6, T35).

Skipped locally if TEST_DATABASE_URL is not set. Runs in CI with pgvector/pgvector:pg16 container.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncGenerator, AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from backend.app.auth.csrf import (
    CSRF_COOKIE_NAME,
    generate_csrf_token,
)
from backend.app.auth.guards import get_current_user
from backend.app.db.models import (
    AppUser,
    Batch,
    Cluster,
    ContentRelease,
    LLMCall,
    Move,
    Scene,
    ScheduledJob,
    Teacher,
    TemplateSend,
    Turn,
)
from backend.app.db.session import get_db_session
from backend.app.main import app

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL not set (runs in CI with real pgvector/pgvector:pg16)",
)


def get_async_db_url() -> str:
    url = TEST_DATABASE_URL or ""
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if "postgresql+psycopg2://" in url:
        return url.replace("postgresql+psycopg2://", "postgresql+asyncpg://")
    return url


@pytest.fixture
async def db_session_factory() -> AsyncGenerator[async_sessionmaker[AsyncSession], None]:
    async_url = get_async_db_url()
    engine = create_async_engine(async_url, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with factory() as session:
        await session.merge(Cluster(id="KNP-C01", name="Test Cluster"))
        await session.merge(Batch(id="KNP-B1", name="Test Batch"))
        await session.commit()

    try:
        yield factory
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_admin_dashboard_postgres_end_to_end(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Verifies full admin dashboard metrics, fast-forward, and demo reset on PostgreSQL."""
    now = datetime.now(UTC)

    # 1. Seed admin, demo teacher, active content release, turns, LLM calls, template sends, and jobs
    async with db_session_factory() as session:
        admin_user = AppUser(
            id=uuid.uuid4(),
            username=f"admin_{uuid.uuid4().hex[:6]}",
            password_hash="fake",
            role="admin",
            display_name="परीक्षण एडमिन",
        )
        demo_teacher = Teacher(
            id=uuid.uuid4(),
            name="डेमो शिक्षक राजेश",
            school_id="SCH-DEMO-01",
            district="Kanpur Nagar",
            cluster_id="KNP-C01",
            is_demo=True,
            onboarding_state="COMPLETE",
        )
        session.add_all([admin_user, demo_teacher])
        await session.flush()

        # Seed Active ContentRelease
        release = ContentRelease(
            id=f"rel_{uuid.uuid4().hex[:6]}",
            notes="टेस्ट रिलीज़",
            published_by=admin_user.id,
            is_active=True,
        )
        session.add(release)
        await session.flush()

        # Seed Move
        move = Move(
            id=f"move_{uuid.uuid4().hex[:6]}",
            release_id=release.id,
            domain="math",
            title_hi="परीक्षण तरीका",
            status="approved",
            payload={"id": "test_move"},
            approvals=[],
        )
        session.add(move)

        # Seed Scene & Turn for demo teacher
        scene = Scene(
            id=uuid.uuid4(),
            teacher_id=demo_teacher.id,
            move_id=move.id,
            status="ended",
            mode="normal",
            engine_state={},
        )
        session.add(scene)
        await session.flush()

        turn = Turn(
            id=uuid.uuid4(),
            teacher_id=demo_teacher.id,
            scene_id=scene.id,
            idx=0,
            role="teacher",
            transcript="नमस्ते बच्चों",
            latency_ms=120,
        )
        session.add(turn)

        # Seed LLM calls with outcomes and tokens
        llm1 = LLMCall(
            id=uuid.uuid4(),
            role="coach",
            latency_ms=450,
            outcome="pass",
            input_tokens=100,
            output_tokens=50,
        )
        llm2 = LLMCall(
            id=uuid.uuid4(),
            role="coach",
            latency_ms=650,
            outcome="pass",
            input_tokens=120,
            output_tokens=60,
        )
        llm3 = LLMCall(
            id=uuid.uuid4(),
            role="child_voice",
            latency_ms=300,
            outcome="retry",
            input_tokens=80,
            output_tokens=40,
        )
        session.add_all([llm1, llm2, llm3])

        # Seed TemplateSend
        tmpl = TemplateSend(
            id=uuid.uuid4(),
            teacher_id=demo_teacher.id,
            template_name="weekly_prompt_rehearse",
            category="utility",
            est_cost_inr=0.450,
            sent_at=now,
        )
        session.add(tmpl)

        # Seed ScheduledJob for fast-forward
        job = ScheduledJob(
            id=uuid.uuid4(),
            kind="prompt_rehearse",
            run_at=now + timedelta(hours=12),
            payload={"teacher_id": str(demo_teacher.id), "move_id": move.id},
            status="pending",
        )
        session.add(job)
        await session.commit()

    async def override_db() -> AsyncIterator[AsyncSession]:
        async with db_session_factory() as s:
            yield s

    async def override_user() -> AppUser:
        return admin_user

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_current_user] = override_user

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # 1. Test GET /admin dashboard rendering
        res = await client.get("/admin")
        assert res.status_code == 200
        html = res.text
        assert "अभ्यास एडमिन डैशबोर्ड" in html
        assert release.id in html
        assert "coach" in html
        assert "child_voice" in html
        assert "weekly_prompt_rehearse" in html
        assert "prompt_rehearse" in html
        assert demo_teacher.name in html

        # 2. Test POST /admin/fast-forward
        csrf = generate_csrf_token()
        client.cookies.set(CSRF_COOKIE_NAME, csrf)

        res_ff = await client.post(
            "/admin/fast-forward",
            data={"csrf_token": csrf, "teacher_id": str(demo_teacher.id)},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            follow_redirects=False,
        )
        assert res_ff.status_code == 303
        assert "/admin?msg=ff_ok" in res_ff.headers["location"]

        # Verify job advanced to done or attempted in database
        async with db_session_factory() as verify_session:
            updated_job = await verify_session.get(ScheduledJob, job.id)
            assert updated_job is not None
            # Fast-forward advanced run_at to now or executed it
            assert updated_job.run_at <= now + timedelta(seconds=10)

        # 3. Test POST /admin/reset-demo
        csrf_reset = generate_csrf_token()
        client.cookies.set(CSRF_COOKIE_NAME, csrf_reset)

        res_reset = await client.post(
            "/admin/reset-demo",
            data={"csrf_token": csrf_reset},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            follow_redirects=False,
        )
        assert res_reset.status_code == 303
        assert "/admin?msg=reset_ok" in res_reset.headers["location"]

        # Verify in database: demo scene and turn were deleted
        async with db_session_factory() as verify_session:
            db_scene = await verify_session.get(Scene, scene.id)
            assert db_scene is None
            db_turn = await verify_session.get(Turn, turn.id)
            assert db_turn is None

    app.dependency_overrides.clear()
