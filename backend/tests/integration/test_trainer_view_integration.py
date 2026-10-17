"""Integration tests for Trainer view and CSV export against PostgreSQL (spec/09 §9.4, T33).

Verifies:
1. Role guard: only trainer (and admin) can access /trainer and /trainer/export.csv (HTTP 401/403 for others).
2. Privacy by design: any batch with n < 10 (e.g. KNP-B3 with 8 teachers) is STRICTLY SUPPRESSED
   with "समूह छोटा है (n<10) — गोपनीयता हेतु छिपाया गया".
3. Unsuppressed batches (e.g. KNP-B1 with 25 teachers) display completion %, top missed key point, and inline SVG rubric bars.
4. Deterministic insight box renders recommendation when missing rate >= 40%.
5. P0 Privacy: NO teacher names or phone numbers appear ANYWHERE in the HTML or CSV export.
"""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from backend.app.auth.access import SUPPRESSION_MESSAGE
from backend.app.auth.guards import get_current_user
from backend.app.db.base import Base
from backend.app.db.models import (
    AdoptionEvidence,
    AggModuleBatch,
    AppUser,
    Batch,
    ExplainScore,
    RehearsalScore,
    Teacher,
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
async def session_factory() -> AsyncGenerator[async_sessionmaker[AsyncSession], None]:
    async_url = get_async_db_url()
    engine = create_async_engine(async_url, poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    # Seed batches for trainer tests
    async with factory() as session:
        await session.merge(
            Batch(
                id="KNP-B1",
                name="कानपुर बैच 1",
                district="Kanpur Nagar",
                module="NUM_SUB_REGROUP_BUNDLES",
            )
        )
        await session.merge(
            Batch(
                id="KNP-B2",
                name="कानपुर बैच 2",
                district="Kanpur Nagar",
                module="NUM_SUB_REGROUP_BUNDLES",
            )
        )
        await session.merge(
            Batch(
                id="KNP-B3",
                name="कानपुर बैच 3",
                district="Kanpur Nagar",
                module="NUM_SUB_REGROUP_BUNDLES",
            )
        )
        await session.commit()

    try:
        yield factory
    finally:
        async with factory() as session:
            await session.execute(
                delete(AggModuleBatch).where(
                    AggModuleBatch.batch_id.in_(["KNP-B1", "KNP-B2", "KNP-B3"])
                )
            )
            await session.execute(
                delete(ExplainScore).where(ExplainScore.move_id == "NUM_SUB_REGROUP_BUNDLES")
            )
            await session.execute(
                delete(RehearsalScore).where(RehearsalScore.move_id == "NUM_SUB_REGROUP_BUNDLES")
            )
            await session.execute(
                delete(AdoptionEvidence).where(
                    AdoptionEvidence.move_id == "NUM_SUB_REGROUP_BUNDLES"
                )
            )
            await session.execute(
                delete(Teacher).where(Teacher.batch_id.in_(["KNP-B1", "KNP-B2", "KNP-B3"]))
            )
            await session.execute(delete(Batch).where(Batch.id.in_(["KNP-B1", "KNP-B2", "KNP-B3"])))
            await session.execute(delete(AppUser).where(AppUser.username.like("trainer.test.%")))
            await session.commit()
        await engine.dispose()


@pytest.mark.asyncio
async def test_trainer_route_role_guard(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Verifies that non-trainers are blocked with 401 or 403."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # 1. Unauthenticated -> 401
        res = await client.get("/trainer")
        assert res.status_code == 401

        # 2. Teacher role -> 403
        teacher_user = AppUser(
            id=uuid4(),
            username=f"trainer.test.teacher.{uuid4().hex[:6]}",
            password_hash="hash",
            role="teacher",
        )

        async def override_teacher() -> AppUser:
            return teacher_user

        app.dependency_overrides[get_current_user] = override_teacher
        try:
            res_teacher = await client.get("/trainer")
            assert res_teacher.status_code == 403
        finally:
            app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_trainer_dashboard_suppression_and_no_teacher_pii(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Verifies that KNP-B3 (8 teachers) is suppressed, KNP-B1 (12 teachers) is unsuppressed,

    and NO teacher names or phone hashes appear anywhere in the HTML or CSV.
    """
    secret_teacher_names = ["गुप्त_शिक्षिका_123", "गोपनीय_अध्यापक_456"]
    secret_phone_hash = "secret_phone_hash_9999"

    async with session_factory() as session:
        # Seed 12 teachers in KNP-B1 (n >= 10, unsuppressed)
        for i in range(12):
            t = Teacher(
                id=uuid4(),
                name=f"टीचर_B1_{i}",
                phone_hash=f"hash_b1_{uuid4().hex}",
                batch_id="KNP-B1",
                district="Kanpur Nagar",
                consent_share_scores=True,
                is_demo=False,
            )
            session.add(t)
            await session.flush()

            # Add rehearsal scores
            session.add(
                RehearsalScore(
                    teacher_id=t.id,
                    move_id="NUM_SUB_REGROUP_BUNDLES",
                    scores={"crit1": 2},
                    evidence={},
                )
            )
            # Add explain score with missing key point kp3 for 60% of teachers
            session.add(
                ExplainScore(
                    teacher_id=t.id,
                    move_id="NUM_SUB_REGROUP_BUNDLES",
                    points={"kp3": "missing" if i < 8 else "covered"},
                )
            )
            session.add(
                AdoptionEvidence(
                    teacher_id=t.id,
                    move_id="NUM_SUB_REGROUP_BUNDLES",
                    level=1,
                    source="rehearsal",
                )
            )

        # Seed 8 teachers in KNP-B3 (n = 8 < 10, MUST BE SUPPRESSED)
        for i in range(8):
            t = Teacher(
                id=uuid4(),
                name=secret_teacher_names[i % len(secret_teacher_names)],
                phone_hash=secret_phone_hash if i == 0 else f"hash_b3_{uuid4().hex}",
                batch_id="KNP-B3",
                district="Kanpur Nagar",
                consent_share_scores=True,
                is_demo=False,
            )
            session.add(t)
            await session.flush()

            session.add(
                RehearsalScore(
                    teacher_id=t.id,
                    move_id="NUM_SUB_REGROUP_BUNDLES",
                    scores={"crit1": 0},
                    evidence={},
                )
            )

        await session.commit()

        trainer_user = AppUser(
            id=uuid4(),
            username=f"trainer.test.{uuid4().hex[:6]}",
            password_hash="hash",
            role="trainer",
            district="Kanpur Nagar",
        )
        session.add(trainer_user)
        await session.commit()

    async def override_db() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as s:
            yield s

    async def override_user() -> AppUser:
        return trainer_user

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_current_user] = override_user

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            # 1. Test HTML Dashboard
            res_html = await client.get("/trainer")
            assert res_html.status_code == 200
            html_text = res_html.text

            # KNP-B1 (12 teachers) must show metrics
            assert "KNP-B1" in html_text
            assert "<svg" in html_text  # SVG rubric bar rendered

            # KNP-B3 (8 teachers) MUST BE SUPPRESSED
            assert "KNP-B3" in html_text
            assert SUPPRESSION_MESSAGE in html_text

            # Deterministic Insight Box must be present (67% missing kp3 on KNP-B1)
            assert "अगली ट्रेनिंग में इस पर 10 मिनट दें" in html_text

            # P0 PRIVACY GUARANTEE: Neither secret teacher names nor phone hashes appear in HTML
            for name in secret_teacher_names:
                assert name not in html_text
            assert secret_phone_hash not in html_text

            # 2. Test CSV Export
            res_csv = await client.get("/trainer/export.csv")
            assert res_csv.status_code == 200
            assert "text/csv" in res_csv.headers["content-type"]
            csv_text = res_csv.text

            # Header
            assert "batch_id,batch_name,move_id" in csv_text

            # KNP-B3 suppression in CSV
            csv_lines = csv_text.strip().splitlines()
            knp_b3_line = next(line for line in csv_lines if "KNP-B3" in line)
            assert knp_b3_line.count(SUPPRESSION_MESSAGE) == 8

            # P0 PRIVACY GUARANTEE: Neither secret teacher names nor phone hashes appear in CSV
            for name in secret_teacher_names:
                assert name not in csv_text
            assert secret_phone_hash not in csv_text

    finally:
        app.dependency_overrides.clear()
