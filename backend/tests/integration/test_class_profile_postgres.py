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

            # the module cards say why they were chosen, and her modules come first
            assert 'data-because="NUM_SUB_REGROUP_BUNDLES"' in home.text
            assert 'data-because="NUM_ADD_CARRY_BUNDLES"' not in home.text
            assert home.text.index('id="module-NUM_PLACE_VALUE_BUNDLES"') < home.text.index(
                'id="module-NUM_ADD_CARRY_BUNDLES"'
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


@pytest.mark.asyncio
async def test_saving_and_clearing_reorders_the_stored_path_and_helped_is_stored(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    from backend.app.db.models import ClassOutcome, MovePath
    from backend.app.sessions.path import MovePathEntry
    from backend.app.sessions.repository import SessionRepository

    teacher_id = uuid4()
    original = [
        "NUM_PLACE_VALUE_BUNDLES",
        "NUM_SUB_REGROUP_BUNDLES",
        "NUM_ADD_CARRY_BUNDLES",
        "LIT_MATRA_BLENDING",
    ]
    async with session_factory() as session:
        service = SessionService(db_session=session)
        await _ready_teacher(service, teacher_id)
        await SessionRepository(session).record_move_path(
            teacher_id,
            [MovePathEntry(i, m, f"month_rank={i}") for i, m in enumerate(original, start=1)],
        )

        async def stored_path() -> list[str]:
            rows = (
                (
                    await session.execute(
                        select(MovePath)
                        .where(MovePath.teacher_id == teacher_id)
                        .order_by(MovePath.position)
                    )
                )
                .scalars()
                .all()
            )
            return [str(r.move_id) for r in rows]

        try:
            await service.set_class_struggles(teacher_id, ["NUM_ADD_CARRY", "LIT_MATRA_DROP"])
            await session.commit()
            assert (await stored_path())[:2] == [
                "NUM_ADD_CARRY_BUNDLES",
                "LIT_MATRA_BLENDING",
            ]
            assert len(await stored_path()) == 4

            await service.set_class_struggles(teacher_id, [])
            await session.commit()
            assert await stored_path() == original

            # "did it help your class?" lands in class_outcome (constraint: yes / some / no)
            await SessionRepository(session).record_class_outcome(
                teacher_id, "NUM_ADD_CARRY_BUNDLES", "some", ["NUM_ADD_CARRY"]
            )
            rows = (
                (
                    await session.execute(
                        select(ClassOutcome).where(ClassOutcome.teacher_id == teacher_id)
                    )
                )
                .scalars()
                .all()
            )
            assert [(r.answer, r.struggle_ids) for r in rows] == [("some", ["NUM_ADD_CARRY"])]
            with pytest.raises(Exception, match="check_class_outcome_answer"):
                await SessionRepository(session).record_class_outcome(
                    teacher_id, "NUM_ADD_CARRY_BUNDLES", "maybe", []
                )
        finally:
            await session.rollback()
            await session.execute(delete(Teacher).where(Teacher.id == teacher_id))
            await session.commit()


async def _skill_teacher(
    session_factory: async_sessionmaker[AsyncSession], *, consent: bool, skills: list[str]
) -> UUID:
    async with session_factory() as session:
        teacher = Teacher(
            id=uuid4(),
            name="कौशल",
            phone_hash=f"ph_{uuid4().hex}",
            district="SKILL_TEST_DISTRICT",
            consent_share_scores=consent,
            teaching_skills=skills,
        )
        session.add(teacher)
        await session.commit()
        return teacher.id


@pytest.mark.asyncio
async def test_skills_page_saves_a_closed_list_of_at_most_two_and_can_clear(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        teacher = Teacher(id=uuid4(), name="पृष्ठ", phone_hash=f"ph_{uuid4().hex}")
        session.add(teacher)
        await session.flush()
        user = AppUser(
            id=uuid4(),
            username=f"teacher.skill.{uuid4().hex[:6]}",
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

    async def stored() -> list[str]:
        async with session_factory() as s:
            row = (await s.execute(select(Teacher).where(Teacher.id == teacher_id))).scalar_one()
            await s.refresh(row)
            return list(row.teaching_skills)

    app.dependency_overrides[get_db_session] = real_db
    app.dependency_overrides[get_current_user] = fake_user
    csrf = {"headers": {"X-CSRF-Token": "t"}, "cookies": {"abhyas_csrf": "t"}}
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            page = await client.get("/teacher/class")
            assert page.status_code == 200
            assert page.text.count('name="skill"') == 6  # five skills and "something else"
            saved = await client.post(
                "/teacher/class/skills/save",
                data={"skill": ["BOGUS", "asks_to_explain", "probes_with_followup", "other"]},
                follow_redirects=False,
                **csrf,
            )
            assert saved.status_code == 303
            # closed list: the made-up id is dropped; two kept, "other" cannot sit next to a skill
            assert await stored() == ["asks_to_explain", "probes_with_followup"]
            shown = await client.get("/teacher/class?skills_saved=1")
            assert 'data-skill="asks_to_explain"' in shown.text
            assert shown.text.count("class-src") >= 2  # each skill shows its handbook page
            changed = await client.post(
                "/teacher/class/skills/save",
                data={"skill": ["other"]},
                follow_redirects=False,
                **csrf,
            )
            assert changed.status_code == 303 and await stored() == ["other"]
            cleared = await client.post(
                "/teacher/class/skills/clear", follow_redirects=False, **csrf
            )
            assert cleared.status_code == 303 and await stored() == []
            started = await client.post(
                "/teacher/class/skills/start", follow_redirects=False, **csrf
            )
            assert started.status_code == 303
            async with session_factory() as s:
                ctx = await SessionService(db_session=s).get_or_create_context(teacher_id)
                assert ctx.skill_stage == "asking"
    finally:
        app.dependency_overrides.clear()
        async with session_factory() as s:
            await s.execute(delete(AppUser).where(AppUser.id == user_id))
            await s.execute(delete(Teacher).where(Teacher.id == teacher_id))
            await s.commit()


@pytest.mark.asyncio
async def test_trainer_skill_aggregate_hides_below_ten_and_counts_only_consenting_teachers(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    from backend.app.reports.teaching_skills import teaching_skill_summary

    ids: list[UUID] = []
    try:
        for _ in range(9):
            ids.append(
                await _skill_teacher(session_factory, consent=True, skills=["asks_to_explain"])
            )
        ids.append(await _skill_teacher(session_factory, consent=False, skills=["other"]))
        ids.append(await _skill_teacher(session_factory, consent=True, skills=[]))
        async with session_factory() as s:
            few = await teaching_skill_summary(
                s, district="SKILL_TEST_DISTRICT", suppress_below=settings.AGGREGATION_SUPPRESSION_N
            )
        assert few.n_teachers == 9 and few.suppressed and few.rows == []  # nothing at 9
        ids.append(
            await _skill_teacher(
                session_factory, consent=True, skills=["asks_to_explain", "probes_with_followup"]
            )
        )
        async with session_factory() as s:
            many = await teaching_skill_summary(
                s, district="SKILL_TEST_DISTRICT", suppress_below=settings.AGGREGATION_SUPPRESSION_N
            )
            other_district = await teaching_skill_summary(
                s, district="NOWHERE", suppress_below=settings.AGGREGATION_SUPPRESSION_N
            )
        assert many.n_teachers == 10 and not many.suppressed
        counts = {r.skill_id: r.teachers for r in many.rows}
        assert counts == {"asks_to_explain": 10, "probes_with_followup": 1}  # "other" not counted
        assert other_district.n_teachers == 0
    finally:
        async with session_factory() as s:
            await s.execute(delete(Teacher).where(Teacher.id.in_(ids)))
            await s.commit()
