"""The two last adds on a really seeded PostgreSQL database: demo history for "My progress" and the
cohort's "worked" answers behind the peer line. Skipped without TEST_DATABASE_URL.

One scratch database is migrated and seeded once; the tests read it through the real repository,
service and report builders. Nothing a test changes is kept (the session rolls back).
"""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator, Iterator
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from test_seed_postgres import _run, _sync_url

from backend.app.class_profile import followup, my_progress
from backend.app.config import settings
from backend.app.core.messages import get_message, reset_ui_lang, set_ui_lang
from backend.app.core.types import InboundMessage
from backend.app.db.demo_history import DEMO2_HISTORY, DEMO3_HISTORY
from backend.app.db.demo_loop import STRUGGLE, seed_login_loop
from backend.app.db.models import (
    AppUser,
    ClassFollowup,
    ClassFollowupOutcome,
    RehearsalScore,
    Scene,
    Teacher,
)
from backend.app.db.seed import TEACHER_DEMO2_ID, TEACHER_DEMO3_ID, reset_demo_teacher
from backend.app.reports.arp_digest import build_arp_digest
from backend.app.reports.cluster_pack import build_cluster_pack
from backend.app.reports.reported_vs_observed import build_reported_vs_observed
from backend.app.reports.trainer_aggregates import build_trainer_report
from backend.app.sessions.service import SessionService
from backend.app.sessions.state_machine import SessionStateEnum
from backend.app.sessions.titles import move_title

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="TEST_DATABASE_URL not set")

N = settings.AGGREGATION_SUPPRESSION_N
FIXED = datetime.now(UTC).replace(microsecond=0)


@pytest.fixture(scope="module")
def seeded_db() -> Iterator[str]:
    db_name = f"abhyas_last_{uuid4().hex[:10]}"
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
        await s.rollback()
    await engine.dispose()


@pytest.fixture(autouse=True)
def flags(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "DEMO_MODE", True)
    monkeypatch.setattr(followup, "utcnow", lambda: FIXED)


@pytest.fixture(params=["hi", "en"])
def lang(request: pytest.FixtureRequest) -> Iterator[str]:
    token = set_ui_lang(request.param)
    yield request.param
    reset_ui_lang(token)


async def count(session: AsyncSession, model: type, *where: object) -> int:
    stmt = select(func.count()).select_from(model).where(*where)
    return int((await session.execute(stmt)).scalar_one())


def tap(teacher_id: object, button: str) -> InboundMessage:
    return InboundMessage(
        channel="web",
        channel_msg_id=f"m-{uuid4().hex[:8]}",
        teacher_id=teacher_id,  # type: ignore[arg-type]
        kind="button",
        text=None,
        button_id=button,
        received_at=datetime.now(UTC),
    )


async def log_in(session: AsyncSession, login: str, teacher_id: object) -> SessionService:
    await reset_demo_teacher(session, login)  # what a demo login does
    await session.commit()
    return SessionService(db_session=session)


# ── L1d: demo history ───────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_demo2_and_demo3_have_labelled_history_that_shows_a_trend(
    session: AsyncSession,
) -> None:
    for teacher_id, history in ((TEACHER_DEMO2_ID, DEMO2_HISTORY), (TEACHER_DEMO3_ID, DEMO3_HISTORY)):
        teacher = await session.get(Teacher, teacher_id)
        assert teacher is not None and teacher.is_demo  # labelled demo data
        service = SessionService(db_session=session)
        rows = await service.repo.rehearsal_history(teacher_id, settings.MY_PROGRESS_HISTORY_MAX)
        assert len(rows) >= len(history) >= 3  # the cohort seed adds one older practice of its own
        first, last = my_progress.pick_pair(rows) or (None, None)
        assert first is not None and last is not None
        before, after = my_progress.facts_of(first), my_progress.facts_of(last)
        assert before["told"] is True and after["told"] is False  # stopped telling the answer
        assert before["asked"] is False and after["asked"] is True


@pytest.mark.asyncio
async def test_reset_removes_a_judge_made_rehearsal_and_restores_the_demo_history(
    session: AsyncSession,
) -> None:
    service = await log_in(session, "teacher.demo2", TEACHER_DEMO2_ID)
    base = await count(session, RehearsalScore, RehearsalScore.teacher_id == TEACHER_DEMO2_ID)
    scene_id = uuid4()
    session.add(
        Scene(
            id=scene_id,
            teacher_id=TEACHER_DEMO2_ID,
            move_id="NUM_SUB_REGROUP_BUNDLES",
            engine_state={},
            status="ended",
        )
    )
    await session.flush()
    session.add(
        RehearsalScore(
            id=uuid4(),
            teacher_id=TEACHER_DEMO2_ID,
            scene_id=scene_id,
            move_id="NUM_SUB_REGROUP_BUNDLES",
            attempt=1,
            scores={},
            evidence={},
        )
    )
    await session.commit()
    assert await count(session, RehearsalScore, RehearsalScore.teacher_id == TEACHER_DEMO2_ID) == base + 1
    await service.repo.session.execute(text("select 1"))
    await reset_demo_teacher(session, "teacher.demo2")  # the next login
    await session.commit()
    assert await count(session, RehearsalScore, RehearsalScore.teacher_id == TEACHER_DEMO2_ID) == base
    assert await count(session, Scene, Scene.id == scene_id) == 0


@pytest.mark.asyncio
async def test_no_history_is_created_outside_demo_mode(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    await reset_demo_teacher(session, "teacher.demo3")
    monkeypatch.setattr(settings, "DEMO_MODE", False)
    await session.execute(text("delete from rehearsal_score where model = 'demo'"))
    await seed_login_loop(session, TEACHER_DEMO3_ID, FIXED)
    assert await count(session, RehearsalScore, RehearsalScore.model == "demo") == 0


# ── L1: the real tap on demo2 ───────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_demo2_my_progress_message_shows_the_trend_and_a_next_step(
    session: AsyncSession, lang: str
) -> None:
    service = await log_in(session, "teacher.demo2", TEACHER_DEMO2_ID)
    ctx = await service.get_or_create_context(TEACHER_DEMO2_ID)
    ctx.current_state = SessionStateEnum.DONE
    await service._sync_context_to_db(ctx, TEACHER_DEMO2_ID)
    await session.commit()
    out = await service.handle_inbound(tap(TEACHER_DEMO2_ID, "btn_progress"))
    assert len(out) == 1 and out[0].buttons and len(out[0].buttons) <= 3
    body = out[0].text_hi or ""
    assert get_message("mp_head", n=4).split(",")[0] in body
    assert move_title("NUM_SUB_REGROUP_BUNDLES") in body
    assert get_message("mp_n_named") in body  # the latest practice never named one child
    assert "{" not in body and "mp_" not in body


# ── L2: the peer line on demo2 ──────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_cohort_has_enough_labelled_worked_answers(session: AsyncSession) -> None:
    since = FIXED - timedelta(days=settings.PEER_WORKED_WINDOW_DAYS)
    service = SessionService(db_session=session)
    everyone = await service.repo.peer_worked_teachers(
        STRUGGLE, since, exclude_teacher=TEACHER_DEMO2_ID, is_demo=True
    )
    assert everyone >= N
    cluster = await service.repo.peer_worked_teachers(
        STRUGGLE, since, exclude_teacher=TEACHER_DEMO2_ID, is_demo=True, cluster_id="KNP-C01"
    )
    assert cluster < N  # the demo cluster has only seven consenting teachers: scope falls back
    real = await service.repo.peer_worked_teachers(
        STRUGGLE, since, exclude_teacher=TEACHER_DEMO2_ID, is_demo=False
    )
    assert real == 0  # demo answers never count for a real teacher
    labelled = await session.execute(
        select(func.count())
        .select_from(ClassFollowupOutcome)
        .join(ClassFollowup, ClassFollowup.id == ClassFollowupOutcome.followup_id)
        .join(Teacher, Teacher.id == ClassFollowupOutcome.teacher_id)
        .where(ClassFollowup.struggle_id == STRUGGLE, Teacher.is_demo.is_(False))
    )
    assert labelled.scalar_one() == 0


@pytest.mark.asyncio
async def test_demo2_sees_the_peer_line_after_still_stuck(
    session: AsyncSession, lang: str
) -> None:
    service = await log_in(session, "teacher.demo2", TEACHER_DEMO2_ID)
    await service.offer_followup(TEACHER_DEMO2_ID)
    out = await service.handle_inbound(tap(TEACHER_DEMO2_ID, followup.BTN_STUCK))
    text_all = "\n".join(m.text_hi or "" for m in out)
    n = int(
        (
            await session.execute(
                select(func.count(func.distinct(ClassFollowupOutcome.teacher_id)))
                .join(ClassFollowup, ClassFollowup.id == ClassFollowupOutcome.followup_id)
                .join(Teacher, Teacher.id == ClassFollowupOutcome.teacher_id)
                .where(
                    ClassFollowup.struggle_id == STRUGGLE,
                    ClassFollowupOutcome.outcome == "worked",
                    Teacher.consent_share_scores.is_(True),
                    Teacher.is_demo.is_(True),
                    Teacher.id != TEACHER_DEMO2_ID,
                )
            )
        ).scalar_one()
    )
    assert n >= N
    assert get_message("pw_line", n=n, move=move_title("NUM_SUB_REGROUP_BUNDLES")) in text_all
    assert out[-1].buttons  # the line is never the last thing on screen


# ── L1c: the history is not in any dashboard builder ────────────────────────────────────────
@pytest.mark.asyncio
async def test_no_dashboard_builder_carries_her_rehearsal_history(session: AsyncSession) -> None:
    secrets = [t[0] for h in (DEMO2_HISTORY, DEMO3_HISTORY) for row in h for t in row[1]]
    assert secrets
    arp = AppUser(
        id=uuid4(),
        username="arp.demo",
        role="arp",
        cluster_id="KNP-C01",
        district="Kanpur Nagar",
        display_name="x",
        password_hash="x",
    )
    trainer = AppUser(
        id=uuid4(),
        username="trainer.demo",
        role="trainer",
        cluster_id=None,
        district="Kanpur Nagar",
        display_name="x",
        password_hash="x",
    )
    dumped = [
        repr(await build_arp_digest(session, arp)),
        repr(await build_trainer_report(session, trainer)),
        repr(await build_cluster_pack(session, district="Kanpur Nagar")),
        repr(await build_reported_vs_observed(session, district="Kanpur Nagar")),
    ]
    blob = "\n".join(dumped)
    for words in secrets:
        assert words not in blob
    for heading in ("mp_head", "mp_trend", get_message("mp_too_few", lang="hi")[:12]):
        assert heading not in blob
