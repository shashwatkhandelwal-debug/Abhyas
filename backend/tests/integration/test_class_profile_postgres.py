"""My class on PostgreSQL: chat flow storage, the page, the trainer aggregate, purge.

Skipped locally if TEST_DATABASE_URL is not set.
"""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from backend.app.auth.guards import get_current_user
from backend.app.config import settings
from backend.app.core.types import InboundMessage
from backend.app.db.base import Base
from backend.app.db.models import AppUser, Teacher
from backend.app.db.session import get_db_session
from backend.app.main import app
from backend.app.privacy.purge import purge_teacher_data
from backend.app.reports.class_struggles import class_struggle_summary
from backend.app.sessions.service import SessionService
from backend.app.sessions.state_machine import OnboardingStateEnum, SessionStateEnum

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")

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


def _inbound(
    teacher_id: UUID, text_: str | None = None, button_id: str | None = None
) -> InboundMessage:
    return InboundMessage(
        channel="web",
        channel_msg_id=f"m-{uuid4().hex[:8]}",
        teacher_id=teacher_id,
        kind="button" if button_id else "text",
        text=text_,
        button_id=button_id,
        received_at=datetime.now(UTC),
    )


async def _ready_teacher(service: SessionService, teacher_id: UUID) -> None:
    ctx = await service.get_or_create_context(teacher_id)
    ctx.onboarding_state = OnboardingStateEnum.READY
    ctx.current_move_id = "NUM_SUB_REGROUP_BUNDLES"
    ctx.current_state = SessionStateEnum.LEARN
    ctx.name = "परीक्षण"
    await service._sync_context_to_db(ctx, teacher_id)


async def _stored(session: AsyncSession, teacher_id: UUID) -> list[str]:
    row = (await session.execute(select(Teacher).where(Teacher.id == teacher_id))).scalar_one()
    await session.refresh(row)
    return list(row.class_struggles)


@pytest.mark.asyncio
async def test_chat_flow_saves_only_after_yes_and_survives_a_reload(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    teacher_id = uuid4()
    async with session_factory() as session:
        service = SessionService(db_session=session)
        await _ready_teacher(service, teacher_id)
        try:
            asked = await service.handle_inbound(_inbound(teacher_id, "मेरी कक्षा"))
            assert "कहाँ अटक" in (asked[0].text_hi or "")
            confirm = await service.handle_inbound(_inbound(teacher_id, "हासिल भूल जाते हैं"))
            assert confirm[0].buttons[0].id == "btn_yes"
            assert await _stored(session, teacher_id) == []  # not saved before "yes"
            saved = await service.handle_inbound(_inbound(teacher_id, button_id="btn_yes"))
            assert saved[0].citations
            await session.commit()
            assert await _stored(session, teacher_id) == ["NUM_ADD_CARRY"]
            # a fresh service (a new request) still sees her choice and the weekly state
            fresh = await SessionService(db_session=session).get_or_create_context(teacher_id)
            assert fresh.class_struggles == ["NUM_ADD_CARRY"]
            assert fresh.class_stage == "" and fresh.current_state == SessionStateEnum.LEARN
        finally:
            await session.rollback()
            await session.execute(delete(Teacher).where(Teacher.id == teacher_id))
            await session.commit()


@pytest.mark.asyncio
async def test_class_page_describe_save_clear_and_closed_list(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        teacher = Teacher(id=uuid4(), name="पृष्ठ", phone_hash=f"ph_{uuid4().hex}")
        session.add(teacher)
        await session.flush()
        user = AppUser(
            id=uuid4(),
            username=f"teacher.cls.{uuid4().hex[:6]}",
            password_hash="h",
            role="teacher",
            teacher_id=teacher.id,
        )
        session.add(user)
        await SessionService(db_session=session).get_or_create_context(teacher.id)
        await session.commit()
        teacher_id, user_id = teacher.id, user.id

    async def real_db() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as s:
            yield s

    async def fake_user() -> AppUser:
        async with session_factory() as s:
            return (await s.execute(select(AppUser).where(AppUser.id == user_id))).scalar_one()

    app.dependency_overrides[get_db_session] = real_db
    app.dependency_overrides[get_current_user] = fake_user
    csrf = {"headers": {"X-CSRF-Token": "t"}, "cookies": {"abhyas_csrf": "t"}}
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            page = await client.get("/teacher/class")
            assert page.status_code == 200
            assert page.text.count('name="struggle"') == 9  # the chips
            assert "सूची से चुनिए" in page.text

            described = await client.post(
                "/teacher/class/describe", data={"text": "बच्चे गिनती में गलती करते हैं"}, **csrf
            )
            assert described.status_code == 200
            assert 'data-struggle="NUM_COUNTING"' in described.text
            async with session_factory() as s:
                assert await _stored(s, teacher_id) == []  # describing never saves

            nomatch = await client.post(
                "/teacher/class/describe", data={"text": "मौसम अच्छा है"}, **csrf
            )
            assert "कुछ दर्ज नहीं किया" in nomatch.text

            saved = await client.post(
                "/teacher/class/save",
                data={"ids": "NUM_COUNTING,BOGUS,NUM_ADD_CARRY,NUM_COMPARE,LIT_WRITING"},
                follow_redirects=False,
                **csrf,
            )
            assert saved.status_code == 303
            async with session_factory() as s:
                # closed list: the made-up id is dropped, at most 3 kept, order kept
                assert await _stored(s, teacher_id) == [
                    "NUM_COUNTING",
                    "NUM_ADD_CARRY",
                    "NUM_COMPARE",
                ]
            shown = await client.get("/teacher/class?saved=1")
            assert shown.text.index("NUM_COUNTING") < shown.text.index("NUM_ADD_CARRY")
            assert "अभ्यास का केस नहीं" in shown.text  # counting has no practice case

            ticked = await client.post(
                "/teacher/class/save",
                data={
                    "struggle": ["NUM_SUB_REGROUP", "NUM_PLACE_VALUE"],
                    "order": "NUM_SUB_REGROUP,NUM_PLACE_VALUE",
                },
                follow_redirects=False,
                **csrf,
            )
            assert ticked.status_code == 303
            async with session_factory() as s:
                assert await _stored(s, teacher_id) == ["NUM_SUB_REGROUP", "NUM_PLACE_VALUE"]

            home = await client.get("/teacher/modules")
            assert (
                'id="my-class-card"' in home.text and 'data-struggle="NUM_SUB_REGROUP"' in home.text
            )

            await client.post("/teacher/class/clear", follow_redirects=False, **csrf)
            async with session_factory() as s:
                assert await _stored(s, teacher_id) == []

            no_csrf = await client.post("/teacher/class/save", data={"ids": "NUM_COUNTING"})
            assert no_csrf.status_code == 403
    finally:
        app.dependency_overrides.pop(get_db_session, None)
        app.dependency_overrides.pop(get_current_user, None)
        async with session_factory() as s:
            await s.execute(delete(AppUser).where(AppUser.id == user_id))
            await s.execute(delete(Teacher).where(Teacher.id == teacher_id))
            await s.commit()


async def _cohort(
    session: AsyncSession, district: str, n: int, *, consent: bool = True
) -> list[UUID]:
    ids: list[UUID] = []
    for i in range(n):
        t = Teacher(
            id=uuid4(),
            name=f"गुप्त_{uuid4().hex[:6]}",
            phone_hash=f"ph_{uuid4().hex}",
            district=district,
            consent_share_scores=consent,
            class_struggles=["NUM_COUNTING", "LIT_WRITING"] if i % 2 == 0 else ["NUM_COUNTING"],
        )
        session.add(t)
        ids.append(t.id)
    await session.flush()
    return ids


@pytest.mark.asyncio
async def test_trainer_aggregate_counts_consenting_teachers_and_hides_small_groups(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    district = f"Class District {uuid4().hex[:8]}"
    small = f"Small District {uuid4().hex[:8]}"
    created: list[UUID] = []
    async with session_factory() as session:
        created += await _cohort(session, district, 12)
        created += await _cohort(session, district, 5, consent=False)  # never counted
        created += await _cohort(session, small, 9)
        await session.commit()
        try:
            big = await class_struggle_summary(
                session, district=district, suppress_below=settings.AGGREGATION_SUPPRESSION_N
            )
            assert big.n_teachers == 12 and not big.suppressed
            counts = {r.struggle_id: r.teachers for r in big.rows}
            assert counts == {"NUM_COUNTING": 12, "LIT_WRITING": 6}

            hidden = await class_struggle_summary(
                session, district=small, suppress_below=settings.AGGREGATION_SUPPRESSION_N
            )
            assert hidden.suppressed and hidden.rows == [] and hidden.n_teachers == 9
        finally:
            await session.execute(delete(Teacher).where(Teacher.id.in_(created)))
            await session.commit()


@pytest.mark.asyncio
async def test_purge_removes_the_class_choice(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        (tid,) = await _cohort(session, "Purge District", 1)
        await session.commit()
        await purge_teacher_data(session, tid)
        await session.commit()
        gone = (
            await session.execute(select(Teacher).where(Teacher.id == tid))
        ).scalar_one_or_none()
        assert gone is None
