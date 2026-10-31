"""The connected demo history (regrouping in subtraction) on a really seeded PostgreSQL database.

One scratch database is migrated and seeded once; the tests then read it through the real
repository, service and report builders with a fixed clock. Skipped without TEST_DATABASE_URL.
"""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator, Iterator
from datetime import UTC, date, datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import create_engine, delete, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from test_seed_postgres import _run, _sync_url

from backend.app.class_profile import adaptive, followup
from backend.app.config import settings
from backend.app.core.messages import get_message
from backend.app.db.demo_loop import DEMO_VISIT_TEACHERS, STRUGGLE, seed_login_loop
from backend.app.db.models import (
    ClassCheckin,
    ClassFollowup,
    ClassFollowupOutcome,
    ClassVisitObservation,
    Message,
    Teacher,
)
from backend.app.db.seed import (
    TEACHER_DEMO2_ID,
    TEACHER_DEMO3_ID,
    reset_demo_teacher,
)
from backend.app.reports.cluster_pack import build_cluster_pack
from backend.app.reports.reported_vs_observed import build_reported_vs_observed
from backend.app.sessions.service import SessionService

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="TEST_DATABASE_URL not set")

N = settings.AGGREGATION_SUPPRESSION_N
DISTRICT = "Kanpur Nagar"
FIXED = datetime(2026, 10, 30, 6, 0, tzinfo=UTC)  # a Friday, 11:30 in India
TODAY = date(2026, 10, 30)


@pytest.fixture(scope="module")
def seeded_db() -> Iterator[str]:
    db_name = f"abhyas_loop_{uuid4().hex[:10]}"
    admin = create_engine(_sync_url(), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{db_name}"'))
    try:
        _run(["-m", "alembic", "upgrade", "head"], db_name)
        _run(["-m", "backend.app.db.seed"], db_name)
        yield db_name
    finally:
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{db_name}" WITH (FORCE)'))
        admin.dispose()


@pytest.fixture
async def session(seeded_db: str) -> AsyncGenerator[AsyncSession, None]:
    url = make_url(_sync_url(seeded_db)).set(drivername="postgresql+asyncpg")
    engine = create_async_engine(url.render_as_string(hide_password=False), poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with factory() as s:
        yield s
        await s.rollback()  # nothing a test changes is kept
    await engine.dispose()


@pytest.fixture(autouse=True)
def flags(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "DEMO_MODE", True)
    monkeypatch.setattr(followup, "utcnow", lambda: FIXED)


async def _count(session: AsyncSession, model: type, *where: object) -> int:
    return int(
        (await session.execute(select(func.count()).select_from(model).where(*where))).scalar_one()
    )


# ── every seeded row is demo data ───────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_every_seeded_loop_row_belongs_to_a_demo_teacher_and_is_marked(
    session: AsyncSession,
) -> None:
    assert await _count(session, ClassFollowup) > 0
    assert await _count(session, ClassFollowup, ClassFollowup.is_demo.is_(False)) == 0
    assert (
        await _count(session, ClassVisitObservation, ClassVisitObservation.is_demo.is_(False)) == 0
    )
    for model in (ClassFollowup, ClassFollowupOutcome, ClassVisitObservation):
        real = await session.execute(
            select(func.count())
            .select_from(model)
            .join(Teacher, Teacher.id == model.teacher_id)  # type: ignore[attr-defined]
            .where(Teacher.is_demo.is_(False))
        )
        assert real.scalar_one() == 0


@pytest.mark.asyncio
async def test_arp_demo_cluster_keeps_its_seven_of_twelve_privacy_case(
    session: AsyncSession,
) -> None:
    total = await _count(session, Teacher, Teacher.cluster_id == "KNP-C01")
    shared = await _count(
        session, Teacher, Teacher.cluster_id == "KNP-C01", Teacher.consent_share_scores.is_(True)
    )
    assert (shared, total) == (7, 12)


# ── demo2: the follow-up is due on every login ──────────────────────────────────────────────
@pytest.mark.asyncio
async def test_demo2_follow_up_is_due_on_login_and_offered(session: AsyncSession) -> None:
    assert await reset_demo_teacher(session, "teacher.demo2")  # what a login does
    await seed_login_loop(session, TEACHER_DEMO2_ID, FIXED)  # dates relative to the fixed "now"
    [row] = (
        (
            await session.execute(
                select(ClassFollowup).where(ClassFollowup.teacher_id == TEACHER_DEMO2_ID)
            )
        )
        .scalars()
        .all()
    )
    assert row.struggle_id == STRUGGLE and row.due_date == TODAY and row.is_demo
    [chk] = (
        (
            await session.execute(
                select(ClassCheckin).where(ClassCheckin.teacher_id == TEACHER_DEMO2_ID)
            )
        )
        .scalars()
        .all()
    )
    assert chk.id == row.checkin_id and chk.struggle_ids == [STRUGGLE]
    assert row.offered_at is not None  # fix3 K6: its card is already in the thread
    await session.commit()
    service = SessionService(db_session=session)
    assert await service.offer_followup(TEACHER_DEMO2_ID) == []  # never a second card
    [card] = (
        (
            await session.execute(
                select(Message).where(
                    Message.teacher_id == TEACHER_DEMO2_ID,
                    Message.channel_msg_id == "seed-demo2-followup",
                )
            )
        )
        .scalars()
        .all()
    )
    assert [b["id"] for b in card.buttons] == [
        followup.BTN_WORKED,
        followup.BTN_STUCK,
        followup.BTN_CANT,
    ]
    assert get_message("fu_leadin_most") in card.text  # led in by the stored check-in


@pytest.mark.asyncio
async def test_k6_demo2_card_comes_before_the_rehearsal_block_never_between_turns(
    session: AsyncSession,
) -> None:
    """The seeded follow-up card is the first message of the thread; every rehearsal message follows."""
    assert await reset_demo_teacher(session, "teacher.demo2")
    await session.commit()
    msgs = (
        (
            await session.execute(
                select(Message)
                .where(Message.teacher_id == TEACHER_DEMO2_ID)
                .order_by(Message.created_at, Message.id)
            )
        )
        .scalars()
        .all()
    )
    assert msgs[0].channel_msg_id == "seed-demo2-followup"
    assert [m.channel_msg_id for m in msgs[1:]] == sorted(m.channel_msg_id for m in msgs[1:]), (
        "the rehearsal block keeps its own order after the card"
    )
    assert len(msgs) == 6  # card + the five seeded rehearsal messages
    # opening the chat later offers nothing new in the middle of the scene
    assert await SessionService(db_session=session).offer_followup(TEACHER_DEMO2_ID) == []


@pytest.mark.asyncio
async def test_reset_restores_the_seeded_state_after_a_judge_answers(
    session: AsyncSession,
) -> None:
    await reset_demo_teacher(session, "teacher.demo2")
    await seed_login_loop(session, TEACHER_DEMO2_ID, FIXED)
    await session.commit()
    service = SessionService(db_session=session)
    await service.handle_inbound(_tap(TEACHER_DEMO2_ID, followup.BTN_WORKED))  # the seeded card
    assert (
        await _count(
            session, ClassFollowupOutcome, ClassFollowupOutcome.teacher_id == TEACHER_DEMO2_ID
        )
        == 1
    )
    await reset_demo_teacher(session, "teacher.demo2")  # the next login
    await session.commit()
    assert (
        await _count(
            session, ClassFollowupOutcome, ClassFollowupOutcome.teacher_id == TEACHER_DEMO2_ID
        )
        == 0
    )
    # the reset seeds against the real clock, so ask with the real India date (not FIXED)
    real_today = datetime.now(ZoneInfo("Asia/Kolkata")).date()
    due = await SessionService(db_session=session).repo.next_due_followup(
        TEACHER_DEMO2_ID, real_today
    )
    assert due is not None and due.offered_at is not None and due.struggle_id == STRUGGLE


def _tap(teacher_id, button):  # type: ignore[no-untyped-def]
    from backend.app.core.types import InboundMessage

    return InboundMessage(
        channel="web",
        channel_msg_id=f"m-{uuid4().hex[:8]}",
        teacher_id=teacher_id,
        kind="button",
        text=None,
        button_id=button,
        received_at=datetime.now(UTC),
    )


# ── demo3: the history drives the adaptive path ─────────────────────────────────────────────
@pytest.mark.asyncio
async def test_demo3_gets_a_different_next_practice_than_a_teacher_with_no_history(
    session: AsyncSession,
) -> None:
    await reset_demo_teacher(session, "teacher.demo3")
    await seed_login_loop(session, TEACHER_DEMO3_ID, FIXED)
    await session.commit()
    service = SessionService(db_session=session)
    ctx = await service.get_or_create_context(TEACHER_DEMO3_ID)
    choice = await service._adaptive_choice(ctx, TEACHER_DEMO3_ID, ctx.current_move_id)
    assert choice is not None and choice.move_id == "NUM_SUB_REGROUP_BUNDLES"
    assert choice.signal in ("stuck", "most") and choice.struggle_id == STRUGGLE
    path = [r.move_id for r in await service.repo.get_move_path(TEACHER_DEMO3_ID)]
    none = adaptive.choose_next(
        [m for m in path if m != ctx.current_move_id],
        checkins=[],
        followups=[],
        experience_band=ctx.experience_band,
        now=FIXED,
    )
    assert none is None  # no history: the old order, so a different (unchanged) next practice
    assert adaptive.reason_text(choice).startswith("क्यों अभी यह")


# ── trainer.demo: the cluster pack and "reported vs observed" have content ──────────────────
@pytest.mark.asyncio
async def test_trainer_demo_district_shows_the_pack_and_reported_vs_observed(
    session: AsyncSession,
) -> None:
    pack = await build_cluster_pack(session, district=DISTRICT)
    assert not pack.suppressed and pack.all_demo and pack.items
    rvo = await build_reported_vs_observed(session, district=DISTRICT)
    assert not rvo.suppressed and rvo.all_demo and rvo.n_teachers >= N
    row = next(r for r in rvo.rows if r.struggle_id == STRUGGLE)
    assert row.teachers >= N and row.worked + row.stuck + row.cant == row.teachers
    assert row.observed is not None and row.observed >= N  # the visit notes cover 10 or more
    assert DEMO_VISIT_TEACHERS >= N


@pytest.mark.asyncio
async def test_reported_vs_observed_privacy_message_at_nine_and_content_at_ten(
    session: AsyncSession,
) -> None:
    rows = (
        (
            await session.execute(
                select(ClassFollowupOutcome.teacher_id)
                .join(Teacher, Teacher.id == ClassFollowupOutcome.teacher_id)
                .where(Teacher.consent_share_scores.is_(True), Teacher.district == DISTRICT)
                .distinct()
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) > N
    keep_ten, drop = rows[:N], rows[N:]
    await session.execute(
        Teacher.__table__.update().where(Teacher.id.in_(drop)).values(consent_share_scores=False)
    )
    visits = await session.execute(select(ClassVisitObservation.teacher_id).distinct())
    outside = [t for t in visits.scalars().all() if t not in keep_ten]
    await session.execute(
        Teacher.__table__.update().where(Teacher.id.in_(outside)).values(consent_share_scores=False)
    )
    ten = await build_reported_vs_observed(session, district=DISTRICT)
    assert ten.n_teachers == N and not ten.suppressed
    await session.execute(
        Teacher.__table__.update()
        .where(Teacher.id == keep_ten[0])
        .values(consent_share_scores=False)
    )
    nine = await build_reported_vs_observed(session, district=DISTRICT)
    assert nine.n_teachers == N - 1 and nine.suppressed and nine.rows == []


# ── outside demo mode and with the flags off ────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_no_demo_rows_are_created_outside_demo_mode(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "DEMO_MODE", False)
    await reset_demo_teacher(session, "teacher.demo2")
    await seed_login_loop(session, TEACHER_DEMO2_ID, FIXED)
    assert await _count(session, ClassCheckin, ClassCheckin.teacher_id == TEACHER_DEMO2_ID) == 0
    assert await _count(session, ClassFollowup, ClassFollowup.teacher_id == TEACHER_DEMO2_ID) == 0


@pytest.mark.asyncio
async def test_flags_off_hide_everything(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    await reset_demo_teacher(session, "teacher.demo2")
    await seed_login_loop(session, TEACHER_DEMO2_ID, FIXED)
    await session.commit()
    monkeypatch.setattr(settings, "DEMO_MODE", False)
    for flag in ("FOLLOWUP_ENABLED", "ADAPTIVE_PATH_ENABLED", "OBSERVATION_ENABLED"):
        monkeypatch.setattr(settings, flag, False)
    service = SessionService(db_session=session)
    assert await service.offer_followup(TEACHER_DEMO2_ID) == []
    ctx = await service.get_or_create_context(TEACHER_DEMO3_ID)
    assert await service._adaptive_choice(ctx, TEACHER_DEMO3_ID, ctx.current_move_id) is None
    from backend.app.web import visit_observation

    assert not visit_observation.enabled()
    _ = timedelta


# ── today's focus (FOCUS_CARD_ENABLED, on in demo mode) ─────────────────────────────────────
@pytest.mark.asyncio
async def test_focus_card_demo2_opted_in_waits_for_the_scene_then_once_a_day(
    session: AsyncSession,
) -> None:
    from backend.app.channels.web import WebChannel
    from backend.app.class_profile import focus
    from backend.app.sessions.state_machine import SessionStateEnum

    await reset_demo_teacher(session, "teacher.demo2")
    await seed_login_loop(session, TEACHER_DEMO2_ID, FIXED)
    await session.commit()
    service = SessionService(db_session=session)
    teacher = await service.repo.get_or_create_teacher(TEACHER_DEMO2_ID)
    assert teacher.tomorrow_focus_opt_in is True  # seeded opted in
    # demo2 resumes inside a scene she has started: the card never interrupts it
    assert await service.offer_focus(TEACHER_DEMO2_ID) == []
    ctx = await service.get_or_create_context(TEACHER_DEMO2_ID)
    ctx.current_state = SessionStateEnum.DONE
    ctx.rehearsal_turns_count = 0
    await service._sync_context_to_db(ctx, TEACHER_DEMO2_ID)
    await session.commit()
    out = await service.offer_focus(TEACHER_DEMO2_ID)
    assert len(out) == 1 and out[0].citations
    assert out[0].text_hi.startswith(get_message("focus_card_head"))
    assert [b.id for b in out[0].buttons][-1] == focus.BTN_OFF
    await WebChannel().send(teacher, out, session=session)  # what the chat page does
    await session.commit()
    assert await service.offer_focus(TEACHER_DEMO2_ID) == []  # once today
    await reset_demo_teacher(session, "teacher.demo2")  # the next login clears the thread
    await session.commit()
    teacher = await service.repo.get_or_create_teacher(TEACHER_DEMO2_ID)
    assert teacher.tomorrow_focus_opt_in is True


@pytest.mark.asyncio
async def test_focus_offer_demo3_is_asked_once_and_flag_off_hides_it(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    from backend.app.channels.web import WebChannel
    from backend.app.class_profile import focus

    await reset_demo_teacher(session, "teacher.demo3")
    await session.commit()
    service = SessionService(db_session=session)
    teacher = await service.repo.get_or_create_teacher(TEACHER_DEMO3_ID)
    assert teacher.tomorrow_focus_opt_in is False
    out = await service.offer_focus(TEACHER_DEMO3_ID)
    assert [b.id for b in out[0].buttons] == [focus.BTN_YES, focus.BTN_NO]
    await WebChannel().send(teacher, out, session=session)
    await session.commit()
    assert await service.offer_focus(TEACHER_DEMO3_ID) == []  # not again within the week
    monkeypatch.setattr(settings, "DEMO_MODE", False)
    monkeypatch.setattr(settings, "FOCUS_CARD_ENABLED", False)
    assert await service.offer_focus(TEACHER_DEMO3_ID) == []


# ── what an ARP saw, shown to the teacher (OBSERVATION_TO_TEACHER_ENABLED, on in demo mode) ──
@pytest.mark.asyncio
async def test_visit_note_reaches_demo2_once_after_an_arp_saves_an_observation(
    session: AsyncSession,
) -> None:
    from backend.app.channels.web import WebChannel
    from backend.app.class_profile import visit_note

    await reset_demo_teacher(session, "teacher.demo2")
    await session.commit()
    service = SessionService(db_session=session)
    assert await service.offer_visit_note(TEACHER_DEMO2_ID) == []  # nothing saved yet
    session.add(
        ClassVisitObservation(
            id=uuid4(),
            teacher_id=TEACHER_DEMO2_ID,
            talk_moves=["why_how"],
            practice_seen=True,
            struggle_id=STRUGGLE,
            next_step="hold_answer",
            observed_on=TODAY,
            is_demo=True,
            created_at=datetime.now(UTC),
        )
    )
    await session.commit()
    out = await service.offer_visit_note(TEACHER_DEMO2_ID)
    assert len(out) == 1 and [b.id for b in out[0].buttons] == [visit_note.BTN_OK]
    assert out[0].text_hi.startswith("आपके ARP ने देखा:") and "एक बात आज़माएँ:" in out[0].text_hi
    assert not any(ch.isdigit() for ch in out[0].text_hi)  # a note, never a score
    teacher = await service.repo.get_or_create_teacher(TEACHER_DEMO2_ID)
    await WebChannel().send(teacher, out, session=session)
    await session.commit()
    assert await service.offer_visit_note(TEACHER_DEMO2_ID) == []  # shown once
    await session.execute(
        delete(ClassVisitObservation).where(ClassVisitObservation.teacher_id == TEACHER_DEMO2_ID)
    )
    await session.commit()
