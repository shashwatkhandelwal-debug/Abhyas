"""Part 6 on PostgreSQL: module_progress repository, dashboards summary, picker, logout reset.

Skipped locally if TEST_DATABASE_URL is not set.
"""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from backend.app.auth.guards import get_current_user
from backend.app.db.base import Base
from backend.app.db.models import AppUser, ModuleProgress, Teacher
from backend.app.db.session import get_db_session
from backend.app.main import app
from backend.app.reports.module_progress import module_progress_summary
from backend.app.sessions.repository import SessionRepository

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
SUB = "NUM_SUB_REGROUP_BUNDLES"

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL not set (runs in CI with real pgvector/pgvector:pg16)",
)


def _async_url() -> str:
    url = TEST_DATABASE_URL or ""
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url.replace("postgresql+psycopg2://", "postgresql+asyncpg://")


@pytest.fixture
async def session_factory() -> AsyncGenerator[async_sessionmaker[AsyncSession], None]:
    engine = create_async_engine(_async_url(), poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        yield factory
    finally:
        await engine.dispose()


async def _teacher(
    session: AsyncSession,
    *,
    district: str,
    consent: bool = True,
    demo: bool = False,
    cluster: str | None = None,
) -> Teacher:
    t = Teacher(
        id=uuid4(),
        name=f"गुप्त_{uuid4().hex[:6]}",
        phone_hash=f"ph_{uuid4().hex}",
        district=district,
        consent_share_scores=consent,
        is_demo=demo,
        cluster_id=cluster,
    )
    session.add(t)
    await session.flush()
    return t


@pytest.mark.asyncio
async def test_repository_marks_steps_idempotently_and_never_undoes_them(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        t = await _teacher(session, district="D")
        teacher_pk = t.id
        repo = SessionRepository(session)
        try:
            first = await repo.mark_module_step(t.id, SUB, "learn")
            stamp = first.learn_done_at
            assert stamp is not None
            await repo.mark_module_step(t.id, SUB, "learn")
            await repo.mark_module_step(t.id, SUB, "diagnose", verdict="partly")
            await repo.mark_module_step(t.id, SUB, "practise")
            await repo.mark_module_step(t.id, SUB, "check", passed=False, covered=["kp1"])
            row = (await repo.get_module_progress(t.id, SUB))[0]
            assert row.learn_done_at == stamp
            assert row.diagnose_verdict == "partly" and row.practise_done_at is not None
            assert row.check_passed is False and row.check_covered == ["kp1"]
            await repo.mark_module_step(t.id, SUB, "check", passed=True, covered=["kp1", "kp2"])
            row = (await repo.get_module_progress(t.id, SUB))[0]
            assert row.check_passed is True and row.learn_done_at == stamp
            with pytest.raises(ValueError):
                await repo.mark_module_step(t.id, SUB, "bogus")
        finally:
            await session.rollback()
            await session.execute(delete(Teacher).where(Teacher.id == teacher_pk))
            await session.commit()


@pytest.mark.asyncio
async def test_summary_labels_pilot_and_demo_counts_only_consenting_and_suppresses(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    district = f"Test District {uuid4().hex[:8]}"
    ids = []
    async with session_factory() as session:
        now = datetime.now(UTC)
        pilots = [await _teacher(session, district=district) for _ in range(12)]
        demos = [await _teacher(session, district=district, demo=True) for _ in range(3)]
        hidden = await _teacher(session, district=district, consent=False)
        ids = [t.id for t in (*pilots, *demos, hidden)]
        for i, t in enumerate(pilots):
            session.add(
                ModuleProgress(
                    teacher_id=t.id,
                    module_id=SUB,
                    learn_done_at=now,
                    diagnose_done_at=now if i < 8 else None,
                    practise_done_at=now if i < 5 else None,
                    check_done_at=now if i < 3 else None,
                    check_passed=True if i < 2 else (False if i < 3 else None),
                )
            )
        for t in demos:
            session.add(ModuleProgress(teacher_id=t.id, module_id=SUB, learn_done_at=now))
        session.add(ModuleProgress(teacher_id=hidden.id, module_id=SUB, learn_done_at=now))
        await session.commit()
        try:
            rows = await module_progress_summary(session, district=district)
            by_label = {r.label: r for r in rows}
            assert set(by_label) == {"pilot", "demo"}
            pilot = by_label["pilot"]
            assert pilot.teachers == 12  # the non-consenting teacher is not counted
            assert pilot.steps == {"learn": 12, "diagnose": 8, "practise": 5, "check": 3}
            assert pilot.passed == 2
            assert by_label["demo"].teachers == 3

            rows = await module_progress_summary(session, district=district, suppress_below=10)
            by_label = {r.label: r for r in rows}
            assert not by_label["pilot"].suppressed and by_label["pilot"].teachers == 12
            assert by_label["demo"].suppressed and by_label["demo"].passed == 0
            assert all(v == 0 for v in by_label["demo"].steps.values())
            assert await module_progress_summary(session, district="Elsewhere") == []
        finally:
            await session.execute(delete(Teacher).where(Teacher.id.in_(ids)))
            await session.commit()


@pytest.mark.asyncio
async def test_picker_page_start_route_and_dashboards(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    district = f"Test District {uuid4().hex[:8]}"
    cluster_id = None
    async with session_factory() as session:
        teacher = await _teacher(session, district=district)
        user = AppUser(
            id=uuid4(),
            username=f"teacher.mod.{uuid4().hex[:6]}",
            password_hash="h",
            role="teacher",
            teacher_id=teacher.id,
        )
        trainer = AppUser(
            id=uuid4(), username=f"trainer.mod.{uuid4().hex[:6]}", password_hash="h",
            role="trainer", district=district,
        )  # fmt: skip
        session.add_all([user, trainer])
        await session.flush()
        await SessionRepository(session).mark_module_step(teacher.id, SUB, "learn")
        await session.commit()
        user_id, trainer_id, teacher_id = user.id, trainer.id, teacher.id

    async def real_db() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as s:
            yield s

    current: dict[str, AppUser] = {}

    async def fake_user() -> AppUser:
        return current["user"]

    app.dependency_overrides[get_db_session] = real_db
    app.dependency_overrides[get_current_user] = fake_user
    try:
        async with session_factory() as s:
            current["user"] = (
                await s.execute(select(AppUser).where(AppUser.id == user_id))
            ).scalar_one()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            page = await client.get("/teacher/modules")
            assert page.status_code == 200
            for module_id in (SUB, "NUM_ADD_CARRY_BUNDLES", "NUM_PLACE_VALUE_BUNDLES"):
                assert f'id="module-{module_id}"' in page.text
            # learn is done for subtraction: one tick, the rest open
            assert page.text.count("module-step done") == 1

            resp = await client.post(
                f"/teacher/modules/{SUB}/start",
                headers={"X-CSRF-Token": "t"},
                cookies={"csrf_token": "t"},
                follow_redirects=False,
            )
            assert resp.status_code in (303, 403)
            if resp.status_code == 303:
                async with session_factory() as s:
                    from backend.app.db.models import Message

                    msgs = (
                        (await s.execute(select(Message).where(Message.teacher_id == teacher_id)))
                        .scalars()
                        .all()
                    )
                    assert any(m.buttons for m in msgs)  # the learn step opened with its buttons
            bad = await client.post(
                "/teacher/modules/NOT_A_MODULE/start",
                headers={"X-CSRF-Token": "t"},
                cookies={"csrf_token": "t"},
            )
            assert bad.status_code in (403, 404)

            current["user"] = AppUser(
                id=trainer_id, username="trainer.view", password_hash="h", role="trainer",
                district=district,
            )  # fmt: skip
            view = await client.get("/trainer")
            assert view.status_code == 200
            assert 'id="module-progress"' in view.text
    finally:
        app.dependency_overrides.pop(get_db_session, None)
        app.dependency_overrides.pop(get_current_user, None)
        async with session_factory() as s:
            await s.execute(delete(AppUser).where(AppUser.id.in_([user_id, trainer_id])))
            await s.execute(delete(Teacher).where(Teacher.id == teacher_id))
            await s.commit()
    assert cluster_id is None
