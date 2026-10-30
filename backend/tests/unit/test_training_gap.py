"""Trainer "Where training is not landing": computation, latest-only rule, suppression, flag."""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from backend.app.auth.guards import get_current_user
from backend.app.config import settings
from backend.app.core.messages import get_message, set_ui_lang
from backend.app.db.base import Base
from backend.app.db.models import AppUser, Scene, Teacher, Turn
from backend.app.db.session import get_db_session
from backend.app.main import app
from backend.app.reports.training_gap import (
    HABITS,
    RehearsalFacts,
    build_training_gap,
    compute_gap,
    habits_of,
    training_gap_rows,
)

N = settings.AGGREGATION_SUPPRESSION_N


def fact(
    i: int,
    *,
    move: str = "NUM_SUB_REGROUP_BUNDLES",
    acts: tuple[tuple[str, ...], ...] = (("ask_to_explain",), ("concrete_representation",)),
    addressed: tuple[str | None, ...] = ("ravi", "ravi"),
    group: bool = True,
    concrete: bool = True,
) -> RehearsalFacts:
    return RehearsalFacts(f"t{i}", move, group, acts, addressed, concrete)


def cell(gap, move: str, habit: str):  # type: ignore[no-untyped-def]
    row = next(r for r in gap.rows if r.move_id == move)
    return next(c for c in row.cells if c.habit == habit)


def test_habits_of_one_rehearsal() -> None:
    good = habits_of(fact(1))
    assert good == {
        "told_answer": False,
        "no_ask_why": False,
        "no_named_child": False,
        "no_concrete": False,
    }
    bad = habits_of(fact(2, acts=(("tell_answer",), ("repeat_question",)), addressed=("all", None)))
    assert bad == {
        "told_answer": True,
        "no_ask_why": True,
        "no_named_child": True,
        "no_concrete": True,
    }


def test_one_on_one_and_literacy_habits_are_not_applicable() -> None:
    h = habits_of(fact(1, group=False, concrete=False))
    assert h["no_named_child"] is None and h["no_concrete"] is None


def test_share_count_and_sort_by_largest_gap() -> None:
    facts = [fact(i, move="MOVE_A") for i in range(10)]
    facts += [
        fact(100 + i, move="MOVE_B", acts=(("tell_answer",),) if i < 7 else (("ask_to_explain",),))
        for i in range(10)
    ]
    gap = compute_gap(facts, suppress_below=N, window_days=30)
    told_b = cell(gap, "MOVE_B", "told_answer")
    assert (told_b.n, told_b.count, told_b.share) == (10, 7, 70)
    assert [r.move_id for r in gap.rows] == ["MOVE_B", "MOVE_A"]  # largest gap first
    assert gap.n_teachers == 20 and not gap.empty


@pytest.mark.parametrize(("teachers", "shown"), [(9, False), (10, True)])
def test_cells_suppressed_below_ten(teachers: int, shown: bool) -> None:
    gap = compute_gap([fact(i) for i in range(teachers)], suppress_below=N, window_days=30)
    c = cell(gap, "NUM_SUB_REGROUP_BUNDLES", "told_answer")
    assert (c.share is not None) is shown
    if not shown:
        assert (c.n, c.count, c.share) == (None, None, None)
    rows = training_gap_rows(gap)
    assert all(r["count"] == "" for r in rows) is (not shown)


def test_cell_with_fewer_applicable_teachers_is_suppressed_alone() -> None:
    # 12 teachers rehearsed; only 9 of them in a group scene, so the "named child" cell is withheld
    facts = [fact(i) for i in range(9)] + [fact(50 + i, group=False) for i in range(3)]
    gap = compute_gap(facts, suppress_below=N, window_days=30)
    assert cell(gap, "NUM_SUB_REGROUP_BUNDLES", "told_answer").n == 12
    assert cell(gap, "NUM_SUB_REGROUP_BUNDLES", "no_named_child").n is None


def test_empty_state_and_flat_rows() -> None:
    gap = compute_gap([], suppress_below=N, window_days=30)
    assert gap.empty and gap.rows == [] and training_gap_rows(gap) == []
    full = compute_gap([fact(i) for i in range(10)], suppress_below=N, window_days=30)
    flat = training_gap_rows(full)
    assert len(flat) == len(HABITS) and {r["habit"] for r in flat} == set(HABITS)


def test_hindi_and_english_texts_exist_without_dashes() -> None:
    keys = [
        "ui_gap_title",
        "ui_gap_caption",
        "ui_gap_empty",
        "ui_gap_h_told_answer",
        "ui_gap_h_no_ask_why",
        "ui_gap_h_no_named_child",
        "ui_gap_h_no_concrete",
        "ui_gap_na",
        "ui_gap_card_link",
    ]
    for lang in ("hi", "en"):
        for key in keys:
            text_ = get_message(key, lang=lang, days=30)
            assert text_ and "—" not in text_ and "–" not in text_
    assert get_message("ui_gap_title", lang="en") == "Where training is not landing"
    assert get_message("ui_gap_title", lang="hi") == "प्रशिक्षण कहाँ नहीं पहुँच रहा"
    assert "simulated" in get_message("ui_gap_caption", lang="en", days=30)


# Database: the latest-rehearsal rule, consent, district scope and the page
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
needs_db = pytest.mark.skipif(not TEST_DATABASE_URL, reason="TEST_DATABASE_URL not set")


@pytest.fixture
async def factory() -> AsyncGenerator[async_sessionmaker[AsyncSession], None]:
    url = (TEST_DATABASE_URL or "").replace("postgresql://", "postgresql+asyncpg://", 1)
    engine = create_async_engine(url, poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    await engine.dispose()


async def add_rehearsal(
    session: AsyncSession,
    teacher: Teacher,
    move_id: str,
    acts: list[str],
    *,
    days_ago: float,
    addressed: str = "ravi",
    one_on_one: bool = False,
) -> None:
    scene = Scene(
        id=uuid4(),
        teacher_id=teacher.id,
        move_id=move_id,
        engine_state={"one_on_one": one_on_one},
        status="ended",
        started_at=datetime.now(UTC) - timedelta(days=days_ago),
    )
    session.add(scene)
    await session.flush()
    for idx, act in enumerate(acts, start=1):
        session.add(
            Turn(
                id=uuid4(),
                teacher_id=teacher.id,
                scene_id=scene.id,
                idx=idx,
                role="teacher",
                acts=[act],
                addressed_child=addressed,
            )
        )
    await session.flush()


async def make_teachers(
    session: AsyncSession, district: str, count: int, *, consent: bool = True
) -> list[Teacher]:
    out = []
    for _ in range(count):
        t = Teacher(
            id=uuid4(),
            name="x",
            phone_hash=f"h{uuid4().hex}",
            district=district,
            consent_share_scores=consent,
            is_demo=False,
        )
        session.add(t)
        out.append(t)
    await session.flush()
    return out


@needs_db
@pytest.mark.asyncio
async def test_latest_rehearsal_only_consent_and_window(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    district = f"GapDist-{uuid4().hex[:8]}"
    move = "NUM_SUB_REGROUP_BUNDLES"
    async with factory() as session:
        mine = await make_teachers(session, district, 10)
        no_consent = await make_teachers(session, district, 5, consent=False)
        other = await make_teachers(session, f"{district}-other", 3)
        for t in mine:
            # older rehearsal told the answer; the LATEST one did not: the habit must not count
            await add_rehearsal(session, t, move, ["tell_answer"], days_ago=5)
            await add_rehearsal(session, t, move, ["ask_to_explain"], days_ago=1)
        for t in no_consent + other:
            await add_rehearsal(session, t, move, ["tell_answer"], days_ago=1)
        old = await make_teachers(session, district, 2)
        for t in old:  # outside the 30-day window
            await add_rehearsal(session, t, move, ["tell_answer"], days_ago=45)
        await session.commit()
    async with factory() as session:
        gap = await build_training_gap(session, district=district)
        told = cell(gap, move, "told_answer")
        assert (told.n, told.count, told.share) == (10, 0, 0)  # latest-only; others excluded
        asked = cell(gap, move, "no_ask_why")
        assert asked.count == 0
        none = await build_training_gap(session, district=f"{district}-nobody")
        assert none.empty


@needs_db
@pytest.mark.asyncio
@pytest.mark.parametrize(("count", "shown"), [(9, False), (10, True)])
async def test_database_suppression_at_nine_and_ten(
    factory: async_sessionmaker[AsyncSession], count: int, shown: bool
) -> None:
    district = f"GapDist-{uuid4().hex[:8]}"
    async with factory() as session:
        for t in await make_teachers(session, district, count):
            await add_rehearsal(session, t, "NUM_ADD_CARRY_BUNDLES", ["tell_answer"], days_ago=2)
        await session.commit()
    async with factory() as session:
        gap = await build_training_gap(session, district=district)
        c = cell(gap, "NUM_ADD_CARRY_BUNDLES", "told_answer")
        assert (c.share == 100) is shown and (c.n is None) is (not shown)


@needs_db
@pytest.mark.asyncio
async def test_trainer_page_section_flag_and_link(
    factory: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> None:
    district = f"GapDist-{uuid4().hex[:8]}"
    async with factory() as session:
        for t in await make_teachers(session, district, 10):
            await add_rehearsal(session, t, "NUM_SUB_REGROUP_BUNDLES", ["tell_answer"], days_ago=2)
        await session.commit()
    trainer = AppUser(
        id=uuid4(),
        username=f"trainer.gap.{uuid4().hex[:6]}",
        password_hash="x",
        role="trainer",
        district=district,
    )

    async def as_trainer() -> AppUser:
        return trainer

    async def test_db() -> AsyncGenerator[AsyncSession, None]:
        async with factory() as s:
            yield s

    app.dependency_overrides[get_db_session] = test_db
    app.dependency_overrides[get_current_user] = as_trainer
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            monkeypatch.setattr(settings, "DEMO_MODE", True)
            page = await client.get("/trainer")
            assert page.status_code == 200
            assert 'id="training-gap"' in page.text
            assert "प्रशिक्षण कहाँ नहीं पहुँच रहा" in page.text
            assert "/trainer/move/NUM_SUB_REGROUP_BUNDLES" in page.text
            card = await client.get("/trainer/move/NUM_SUB_REGROUP_BUNDLES")
            assert card.status_code == 200 and "बंडल" in card.text
            assert (await client.get("/trainer/move/NOPE_NOT_A_MOVE")).status_code == 404
            en = await client.get("/trainer", cookies={"abhyas_lang": "en"})
            assert "Where training is not landing" in en.text
            monkeypatch.setattr(settings, "DEMO_MODE", False)
            monkeypatch.setattr(settings, "TRAINING_GAP_ENABLED", False)
            off = await client.get("/trainer")
            assert off.status_code == 200 and 'id="training-gap"' not in off.text
            assert (await client.get("/trainer/move/NUM_SUB_REGROUP_BUNDLES")).status_code == 404
    finally:
        app.dependency_overrides.clear()
        set_ui_lang("hi")
        async with factory() as session:
            await session.execute(delete(AppUser).where(AppUser.username == trainer.username))
            await session.commit()
