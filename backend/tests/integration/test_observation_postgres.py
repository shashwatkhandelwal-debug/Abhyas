"""ARP visit checklist and trainer "reported vs observed" on PostgreSQL.

Skipped locally if TEST_DATABASE_URL is not set (the full gate runs it on a fresh pgvector database).
"""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from markupsafe import escape
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from backend.app.auth.access import SUPPRESSION_MESSAGE
from backend.app.auth.csrf import CSRF_COOKIE_NAME
from backend.app.auth.guards import get_current_user
from backend.app.class_profile.checkin_flow import struggle_label
from backend.app.class_profile.library import load_library
from backend.app.config import settings
from backend.app.core.messages import LANG_COOKIE_NAME, get_message, reset_ui_lang, set_ui_lang
from backend.app.db.base import Base
from backend.app.db.models import (
    AppUser,
    ClassCheckin,
    ClassFollowup,
    ClassFollowupOutcome,
    ClassVisitObservation,
    Cluster,
    Teacher,
)
from backend.app.db.session import get_db_session
from backend.app.main import app
from backend.app.reports.reported_vs_observed import build_reported_vs_observed

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="TEST_DATABASE_URL not set")

CLUSTER = "OBS-C1"
OTHER_CLUSTER = "OBS-C2"
DISTRICT = "Obs District"
N = settings.AGGREGATION_SUPPRESSION_N
LIB = load_library()
STRUGGLE = "NUM_SUB_REGROUP"
OTHER = "NUM_ADD_CARRY"
NAME = "गुप्त_शिक्षक_भ्रमण_55"


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
    async with factory() as session:
        await session.merge(Cluster(id=CLUSTER, name="भ्रमण संकुल 1", district=DISTRICT))
        await session.merge(Cluster(id=OTHER_CLUSTER, name="भ्रमण संकुल 2", district=DISTRICT))
        await session.commit()
    try:
        yield factory
    finally:
        async with factory() as session:
            await session.execute(
                delete(Teacher).where(Teacher.cluster_id.in_([CLUSTER, OTHER_CLUSTER]))
            )
            await session.execute(delete(AppUser).where(AppUser.username.like("obs.test.%")))
            await session.commit()
        await engine.dispose()


async def _teachers(
    session: AsyncSession,
    count: int,
    *,
    cluster: str = CLUSTER,
    consent: bool = True,
    demo: bool = False,
) -> list[UUID]:
    ids: list[UUID] = []
    for _ in range(count):
        t = Teacher(
            id=uuid4(),
            name=NAME,
            phone_hash=f"obs_{uuid4().hex}",
            cluster_id=cluster,
            district=DISTRICT,
            consent_share_scores=consent,
            is_demo=demo,
        )
        session.add(t)
        ids.append(t.id)
    await session.flush()
    return ids


async def _answer(
    session: AsyncSession, teacher_id: UUID, struggle: str, outcome: str, *, days_ago: float = 1
) -> None:
    """A check-in with a struggle, its follow-up and the teacher's answer."""
    moment = datetime.now(UTC) - timedelta(days=days_ago)
    checkin = ClassCheckin(
        id=uuid4(),
        teacher_id=teacher_id,
        module_id="NUM_SUB_REGROUP_BUNDLES",
        outcome="most",
        struggle_ids=[struggle],
        created_at=moment,
    )
    session.add(checkin)
    await session.flush()
    fu = ClassFollowup(
        id=uuid4(),
        teacher_id=teacher_id,
        checkin_id=checkin.id,
        struggle_id=struggle,
        due_date=moment.date(),
        created_at=moment,
    )
    session.add(fu)
    await session.flush()
    session.add(
        ClassFollowupOutcome(
            id=uuid4(),
            teacher_id=teacher_id,
            followup_id=fu.id,
            outcome=outcome,
            created_at=moment,
        )
    )


async def _visit(
    session: AsyncSession, teacher_id: UUID, struggle: str | None, *, days_ago: float = 1
) -> None:
    session.add(
        ClassVisitObservation(
            id=uuid4(),
            teacher_id=teacher_id,
            talk_moves=["why_how"],
            practice_seen=struggle is not None,
            struggle_id=struggle,
            next_step="repeat",
            observed_on=date.today(),
            created_at=datetime.now(UTC) - timedelta(days=days_ago),
        )
    )


# ── the report: suppression at 9 and 10 ─────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_empty_scope(session_factory: async_sessionmaker[AsyncSession]) -> None:
    async with session_factory() as session:
        rvo = await build_reported_vs_observed(session, cluster_id=CLUSTER)
    assert rvo.n_teachers == 0 and not rvo.suppressed and rvo.rows == []


@pytest.mark.asyncio
async def test_nine_teachers_suppress_everything_ten_show_it(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        who = await _teachers(session, N)
        for t in who[: N - 1]:
            await _answer(session, t, STRUGGLE, "worked")
        nine = await build_reported_vs_observed(session, cluster_id=CLUSTER)
        await _answer(session, who[N - 1], STRUGGLE, "stuck")
        ten = await build_reported_vs_observed(session, cluster_id=CLUSTER)
    assert nine.n_teachers == N - 1 and nine.suppressed and nine.rows == []
    assert not ten.suppressed and ten.n_teachers == N
    (row,) = ten.rows
    assert (row.struggle_id, row.teachers, row.worked, row.stuck, row.cant) == (
        STRUGGLE,
        N,
        N - 1,
        1,
        0,
    )


@pytest.mark.asyncio
async def test_a_struggle_needs_n_teachers_and_observed_counts_need_n_visits(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        who = await _teachers(session, N + 2)
        for t in who:
            await _answer(session, t, STRUGGLE, "worked")
        for t in who[: N - 1]:
            await _answer(session, t, OTHER, "cant")  # 9 teachers: never listed
        for t in who[: N - 1]:
            await _visit(session, t, STRUGGLE)  # 9 observed: hidden
        nine_seen = await build_reported_vs_observed(session, cluster_id=CLUSTER)
        await _visit(session, who[N - 1], STRUGGLE)  # 10th teacher observed
        ten_seen = await build_reported_vs_observed(session, cluster_id=CLUSTER)
    assert [r.struggle_id for r in nine_seen.rows] == [STRUGGLE]
    assert nine_seen.rows[0].observed is None
    assert ten_seen.rows[0].observed == N


@pytest.mark.asyncio
async def test_only_consenting_in_scope_and_in_window_teachers_count(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        yes = await _teachers(session, N)
        no = await _teachers(session, 4, consent=False)
        elsewhere = await _teachers(session, 4, cluster=OTHER_CLUSTER)
        for t in yes:
            await _answer(session, t, STRUGGLE, "worked")
            await _answer(session, t, OTHER, "worked", days_ago=40)  # outside the window
        for t in no + elsewhere:
            await _answer(session, t, STRUGGLE, "stuck")
        cluster = await build_reported_vs_observed(session, cluster_id=CLUSTER)
        district = await build_reported_vs_observed(session, district=DISTRICT)
    assert cluster.n_teachers == N and [r.struggle_id for r in cluster.rows] == [STRUGGLE]
    assert cluster.rows[0].stuck == 0
    assert district.n_teachers == N + 4  # the other cluster's consenting teachers, never the rest


@pytest.mark.asyncio
async def test_demo_teachers_are_labelled(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        who = await _teachers(session, N, demo=True)
        for t in who:
            await _answer(session, t, STRUGGLE, "worked")
        all_demo = await build_reported_vs_observed(session, cluster_id=CLUSTER)
        (real,) = await _teachers(session, 1)
        await _answer(session, real, STRUGGLE, "worked")
        mixed = await build_reported_vs_observed(session, cluster_id=CLUSTER)
    assert all_demo.includes_demo and all_demo.all_demo
    assert mixed.includes_demo and not mixed.all_demo


# ── the pages and the form ──────────────────────────────────────────────────────────────────
async def _user(role: str) -> AppUser:
    return AppUser(
        id=uuid4(),
        username=f"obs.test.{role}.{uuid4().hex[:6]}",
        password_hash="hash",
        role=role,
        cluster_id=CLUSTER if role == "arp" else None,
        district=DISTRICT,
    )


async def _call(
    method: str,
    path: str,
    user: AppUser,
    factory: async_sessionmaker[AsyncSession],
    data: dict[str, Any] | None = None,
    lang: str = "hi",
) -> Any:
    async def override_user() -> AppUser:
        return user

    async def override_db() -> AsyncGenerator[AsyncSession, None]:
        async with factory() as s:
            yield s

    app.dependency_overrides[get_current_user] = override_user
    app.dependency_overrides[get_db_session] = override_db
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            async with factory() as s:  # the ARP user is a real row (observations point at it)
                await s.merge(user)
                await s.commit()
            client.cookies.set(LANG_COOKIE_NAME, lang)
            if method == "GET":
                return await client.get(path)
            payload = {"csrf_token": "tok", **(data or {})}
            return await client.post(
                path, data=payload, cookies={CSRF_COOKIE_NAME: "tok"}, follow_redirects=False
            )
    finally:
        app.dependency_overrides.clear()


async def _one_teacher_with_struggle(
    factory: async_sessionmaker[AsyncSession], *, consent: bool = True
) -> UUID:
    async with factory() as session:
        (tid,) = await _teachers(session, 1, consent=consent, demo=True)
        await _answer(session, tid, STRUGGLE, "worked")
        await session.commit()
    return tid


async def _stored(factory: async_sessionmaker[AsyncSession]) -> list[ClassVisitObservation]:
    async with factory() as session:
        rows = await session.execute(select(ClassVisitObservation))
        return list(rows.scalars().all())


@pytest.mark.asyncio
@pytest.mark.parametrize("ui", ["hi", "en"])
async def test_arp_page_has_the_closed_form_and_no_free_text(
    session_factory: async_sessionmaker[AsyncSession], ui: str
) -> None:
    tid = await _one_teacher_with_struggle(session_factory)
    token = set_ui_lang(ui)
    try:
        res = await _call("GET", "/arp", await _user("arp"), session_factory, lang=ui)
    finally:
        reset_ui_lang(token)
    html = res.text
    assert 'id="visit-checklist"' in html
    section = html.split('id="visit-checklist"')[1].split("</section>")[0]
    assert f'id="visit-form-{tid}"' in section
    assert "<textarea" not in section and 'type="text"' not in section
    for move in settings.OBSERVATION_TALK_MOVES:
        assert f'value="{move}"' in section
    assert section.count('type="radio"') == len(settings.OBSERVATION_NEXT_STEPS)
    s = LIB.get(STRUGGLE)
    assert s is not None
    token = set_ui_lang(ui)
    try:
        label = struggle_label(s)
    finally:
        reset_ui_lang(token)
    assert escape(label) in section  # the practice to look for


@pytest.mark.asyncio
async def test_arp_page_lists_only_consenting_teachers_and_has_an_empty_state(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        await _teachers(session, 2, consent=False)
        await session.commit()
    res = await _call("GET", "/arp", await _user("arp"), session_factory)
    assert 'id="visit-checklist-empty"' in res.text and 'id="visit-form-' not in res.text


@pytest.mark.asyncio
async def test_flag_off_hides_the_form_and_the_post_is_404(
    session_factory: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> None:
    tid = await _one_teacher_with_struggle(session_factory)
    monkeypatch.setattr(settings, "OBSERVATION_ENABLED", False)
    monkeypatch.setattr(settings, "DEMO_MODE", False)
    user = await _user("arp")
    page = await _call("GET", "/arp", user, session_factory)
    assert 'id="visit-checklist"' not in page.text
    res = await _call(
        "POST", "/arp/visit", user, session_factory, {"teacher_id": str(tid), "next_step": "repeat"}
    )
    assert res.status_code == 404 and await _stored(session_factory) == []
    trainer = await _call("GET", "/trainer", await _user("trainer"), session_factory)
    assert 'id="reported-observed"' not in trainer.text


@pytest.mark.asyncio
async def test_post_stores_the_closed_fields_and_derives_the_struggle_on_the_server(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    tid = await _one_teacher_with_struggle(session_factory)
    res = await _call(
        "POST",
        "/arp/visit",
        await _user("arp"),
        session_factory,
        {
            "teacher_id": str(tid),
            "talk": ["named_child", "think_time"],
            "practice_seen": "1",
            "next_step": "ask_why",
            "struggle_id": "LIT_WRITING",  # a forged field is ignored
            "notes": "free text is not read",
        },
    )
    assert res.status_code == 303 and res.headers["location"] == "/arp?saved=1&msg=visit"
    (row,) = await _stored(session_factory)
    assert (row.teacher_id, row.talk_moves, row.next_step) == (
        tid,
        ["named_child", "think_time"],
        "ask_why",
    )
    assert row.practice_seen is True and row.struggle_id == STRUGGLE
    assert row.is_demo is True and row.arp_user_id is not None


@pytest.mark.asyncio
async def test_post_validation_and_access(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    tid = await _one_teacher_with_struggle(session_factory)
    quiet = await _one_teacher_with_struggle(session_factory, consent=False)
    async with session_factory() as session:
        (away,) = await _teachers(session, 1, cluster=OTHER_CLUSTER, demo=True)
        await session.commit()
    user = await _user("arp")
    bad_move = await _call(
        "POST",
        "/arp/visit",
        user,
        session_factory,
        {"teacher_id": str(tid), "talk": ["bogus"], "next_step": "repeat"},
    )
    no_step = await _call("POST", "/arp/visit", user, session_factory, {"teacher_id": str(tid)})
    no_consent = await _call(
        "POST",
        "/arp/visit",
        user,
        session_factory,
        {"teacher_id": str(quiet), "next_step": "repeat"},
    )
    elsewhere = await _call(
        "POST",
        "/arp/visit",
        user,
        session_factory,
        {"teacher_id": str(away), "next_step": "repeat"},
    )
    assert (bad_move.status_code, no_step.status_code) == (400, 400)
    assert (no_consent.status_code, elsewhere.status_code) == (403, 404)
    assert await _stored(session_factory) == []


@pytest.mark.asyncio
async def test_practice_seen_without_a_reported_struggle_is_stored_as_not_seen_and_double_post_once(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        (tid,) = await _teachers(session, 1, demo=True)  # no check-in at all
        await session.commit()
    user = await _user("arp")
    form = {"teacher_id": str(tid), "practice_seen": "1", "next_step": "repeat"}
    await _call("POST", "/arp/visit", user, session_factory, form)
    await _call("POST", "/arp/visit", user, session_factory, form)
    (row,) = await _stored(session_factory)
    assert row.practice_seen is False and row.struggle_id is None


async def _seed_ten(factory: async_sessionmaker[AsyncSession], count: int) -> None:
    async with factory() as session:
        who = await _teachers(session, count, demo=True)
        for t in who:
            await _answer(session, t, STRUGGLE, "stuck")
            await _visit(session, t, STRUGGLE)
        await session.commit()


@pytest.mark.asyncio
@pytest.mark.parametrize("ui", ["hi", "en"])
async def test_trainer_page_shows_reported_vs_observed_at_ten_with_caption_and_demo_label(
    session_factory: async_sessionmaker[AsyncSession], ui: str
) -> None:
    await _seed_ten(session_factory, N)
    token = set_ui_lang(ui)
    try:
        res = await _call("GET", "/trainer", await _user("trainer"), session_factory, lang=ui)
        caption = get_message("ui_rvo_caption", days=settings.OBSERVATION_WINDOW_DAYS)
    finally:
        reset_ui_lang(token)
    card = res.text.split('id="reported-observed"')[1].split("</section>")[0]
    assert 'id="rvo-rows"' in card and 'id="rvo-demo"' in card
    assert 'data-kind="observed"' in card and 'data-kind="observed-hidden"' not in card
    assert escape(caption) in card
    assert NAME not in card


@pytest.mark.asyncio
async def test_trainer_page_shows_the_privacy_message_at_nine_and_an_empty_state(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    empty = await _call("GET", "/trainer", await _user("trainer"), session_factory)
    assert 'id="rvo-empty"' in empty.text
    await _seed_ten(session_factory, N - 1)
    res = await _call("GET", "/trainer", await _user("trainer"), session_factory)
    card = res.text.split('id="reported-observed"')[1].split("</section>")[0]
    assert 'id="rvo-suppressed"' in card and escape(SUPPRESSION_MESSAGE) in card
    assert 'id="rvo-rows"' not in card
