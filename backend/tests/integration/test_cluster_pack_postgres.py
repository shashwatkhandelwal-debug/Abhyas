"""Cluster meeting pack on PostgreSQL: counts, privacy rules, the ARP and trainer pages, the print view.

Skipped locally if TEST_DATABASE_URL is not set (the full gate runs it on a fresh pgvector database).
Teachers and check-ins are created in their own cluster and district so nothing else interferes.
"""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from markupsafe import escape
from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from backend.app.auth.access import SUPPRESSION_MESSAGE
from backend.app.auth.guards import get_current_user
from backend.app.class_profile.library import load_library
from backend.app.config import settings
from backend.app.core.messages import get_message, reset_ui_lang, set_ui_lang
from backend.app.db.base import Base
from backend.app.db.models import AppUser, ClassCheckin, Cluster, Teacher
from backend.app.db.session import get_db_session
from backend.app.main import app
from backend.app.reports.cluster_pack import build_cluster_pack

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL not set (runs in CI with real pgvector/pgvector:pg16)",
)

CLUSTER = "PACK-C1"
OTHER_CLUSTER = "PACK-C2"
DISTRICT = "Pack District"
N = settings.AGGREGATION_SUPPRESSION_N
LIB = load_library()
WITH_MOVE = "NUM_SUB_REGROUP"  # move NUM_SUB_REGROUP_BUNDLES
WITH_MOVE_2 = "NUM_ADD_CARRY"
NO_MOVE = "NUM_COUNTING"  # a tip and citations but no practice move
SECRET_NAME = "गुप्त_शिक्षक_पैक_77"


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
        await session.merge(Cluster(id=CLUSTER, name="पैक संकुल 1", district=DISTRICT))
        await session.merge(Cluster(id=OTHER_CLUSTER, name="पैक संकुल 2", district=DISTRICT))
        await session.commit()
    try:
        yield factory
    finally:
        async with factory() as session:
            await session.execute(
                delete(Teacher).where(Teacher.cluster_id.in_([CLUSTER, OTHER_CLUSTER]))
            )
            await session.execute(delete(AppUser).where(AppUser.username.like("pack.test.%")))
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
            name=SECRET_NAME,
            phone_hash=f"pack_{uuid4().hex}",
            cluster_id=cluster,
            district=DISTRICT,
            consent_share_scores=consent,
            is_demo=demo,
        )
        session.add(t)
        ids.append(t.id)
    await session.flush()
    return ids


async def _checkin(
    session: AsyncSession,
    teacher_id: UUID,
    struggle: str | None,
    *,
    outcome: str = "some",
    days_ago: float = 2,
) -> None:
    s = LIB.get(struggle) if struggle else None
    session.add(
        ClassCheckin(
            id=uuid4(),
            teacher_id=teacher_id,
            module_id=(s.move_id or f"OTHER_{s.domain}") if s else "NUM_SUB_REGROUP_BUNDLES",
            outcome=outcome,
            struggle_ids=[struggle] if struggle else [],
            created_at=datetime.now(UTC) - timedelta(days=days_ago),
        )
    )


async def _report(
    session: AsyncSession, who: list[UUID], struggle: str | None, **kw: float | str
) -> None:
    for tid in who:
        await _checkin(session, tid, struggle, **kw)  # type: ignore[arg-type]
    await session.flush()


# ── the builder ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_empty_scope_has_no_pack(session_factory: async_sessionmaker[AsyncSession]) -> None:
    async with session_factory() as session:
        pack = await build_cluster_pack(session, cluster_id=CLUSTER)
    assert pack.n_teachers == 0 and not pack.suppressed and pack.items == []
    assert pack.window_days == 30


@pytest.mark.asyncio
async def test_fewer_than_n_teachers_suppresses_everything(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        who = await _teachers(session, N - 1)
        await _report(session, who, WITH_MOVE)
        pack = await build_cluster_pack(session, cluster_id=CLUSTER)
    assert pack.n_teachers == N - 1 and pack.suppressed
    assert pack.items == []  # not even a count of the struggle


@pytest.mark.asyncio
async def test_a_struggle_needs_n_teachers_and_the_top_two_are_named(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        who = await _teachers(session, N + 6)
        await _report(session, who[: N + 6], WITH_MOVE)  # 16 teachers
        await _report(session, who[: N + 2], WITH_MOVE_2)  # 12 teachers
        await _report(session, who[:N], "LIT_MATRA_DROP")  # 10 teachers: third, not shown
        await _report(session, who[: N - 1], NO_MOVE)  # 9 teachers: below N, never shown
        pack = await build_cluster_pack(session, cluster_id=CLUSTER)
    assert not pack.suppressed and pack.n_teachers == N + 6
    assert [(i.struggle_id, i.teachers) for i in pack.items] == [
        (WITH_MOVE, N + 6),
        (WITH_MOVE_2, N + 2),
    ]
    assert [i.move_id for i in pack.items] == ["NUM_SUB_REGROUP_BUNDLES", "NUM_ADD_CARRY_BUNDLES"]
    assert all(i.move_title for i in pack.items)
    assert pack.practice_item is pack.items[0]


@pytest.mark.asyncio
async def test_a_teacher_counts_once_per_struggle_and_ties_follow_library_order(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        who = await _teachers(session, N)
        for _ in range(3):  # three check-ins each: still one teacher each
            await _report(session, who, WITH_MOVE_2)
        await _report(session, who, WITH_MOVE)
        pack = await build_cluster_pack(session, cluster_id=CLUSTER)
    assert [i.teachers for i in pack.items] == [N, N]
    order = LIB.ids()
    assert [i.struggle_id for i in pack.items] == sorted([WITH_MOVE, WITH_MOVE_2], key=order.index)


@pytest.mark.asyncio
async def test_struggle_without_a_move_says_so_and_keeps_its_tip_and_citations(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        who = await _teachers(session, N)
        await _report(session, who, NO_MOVE)
        pack = await build_cluster_pack(session, cluster_id=CLUSTER)
    (item,) = pack.items
    assert item.move_id is None and item.move_title == "" and pack.practice_item is None
    assert item.tip == LIB.get(NO_MOVE).tip_hi  # type: ignore[union-attr]
    assert item.sources and all("स्रोत" in s for s in item.sources)


@pytest.mark.asyncio
async def test_only_consenting_teachers_in_scope_and_in_the_window_count(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        yes = await _teachers(session, N)
        no_consent = await _teachers(session, 5, consent=False)
        elsewhere = await _teachers(session, 5, cluster=OTHER_CLUSTER)
        await _report(session, yes, WITH_MOVE)
        await _report(session, no_consent, WITH_MOVE)
        await _report(session, elsewhere, WITH_MOVE)
        await _report(session, yes, WITH_MOVE_2, days_ago=31)  # outside the 30-day window
        await _report(session, yes[:3], None, outcome="well")
        pack = await build_cluster_pack(session, cluster_id=CLUSTER)
        district = await build_cluster_pack(session, district=DISTRICT)
    assert pack.n_teachers == N
    assert [(i.struggle_id, i.teachers) for i in pack.items] == [(WITH_MOVE, N)]
    # the district also sees the other cluster's consenting teachers, never the non-consenting
    assert district.n_teachers == N + 5
    assert [(i.struggle_id, i.teachers) for i in district.items] == [(WITH_MOVE, N + 5)]


@pytest.mark.asyncio
async def test_well_outcomes_count_toward_n_but_name_no_struggle(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        who = await _teachers(session, N)
        await _report(session, who, None, outcome="well")
        pack = await build_cluster_pack(session, cluster_id=CLUSTER)
    assert pack.n_teachers == N and not pack.suppressed and pack.items == []


@pytest.mark.asyncio
async def test_demo_teachers_are_labelled(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        demo = await _teachers(session, N, demo=True)
        await _report(session, demo, WITH_MOVE)
        all_demo = await build_cluster_pack(session, cluster_id=CLUSTER)
        real = await _teachers(session, 2, demo=False)
        await _report(session, real, WITH_MOVE)
        mixed = await build_cluster_pack(session, cluster_id=CLUSTER)
    assert all_demo.includes_demo and all_demo.all_demo
    assert mixed.includes_demo and not mixed.all_demo


@pytest.mark.asyncio
@pytest.mark.parametrize("ui", ["hi", "en"])
async def test_labels_follow_the_language(
    session_factory: async_sessionmaker[AsyncSession], ui: str
) -> None:
    token = set_ui_lang(ui)
    try:
        async with session_factory() as session:
            who = await _teachers(session, N)
            await _report(session, who, WITH_MOVE)
            pack = await build_cluster_pack(session, cluster_id=CLUSTER)
    finally:
        reset_ui_lang(token)
    s = LIB.get(WITH_MOVE)
    assert s is not None
    assert pack.items[0].label == (s.label_en if ui == "en" else s.label_hi)
    assert pack.items[0].tip == (s.tip_en if ui == "en" else s.tip_hi)


# ── the pages ───────────────────────────────────────────────────────────────────────────────
async def _user(role: str) -> AppUser:
    return AppUser(
        id=uuid4(),
        username=f"pack.test.{role}.{uuid4().hex[:6]}",
        password_hash="hash",
        role=role,
        cluster_id=CLUSTER if role == "arp" else None,
        district=DISTRICT,
    )


async def _get(  # type: ignore[no-untyped-def]
    path: str,
    user: AppUser,
    session_factory: async_sessionmaker[AsyncSession],
    cookies: dict[str, str] | None = None,
):
    async def override_user() -> AppUser:
        return user

    async def override_db() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as s:
            yield s

    app.dependency_overrides[get_current_user] = override_user
    app.dependency_overrides[get_db_session] = override_db
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            return await client.get(path, cookies=cookies)
    finally:
        app.dependency_overrides.clear()


async def _seed_full(session_factory: async_sessionmaker[AsyncSession]) -> None:
    async with session_factory() as session:
        who = await _teachers(session, N + 4, demo=True)
        await _report(session, who, WITH_MOVE)
        await _report(session, who[: N + 1], NO_MOVE)
        await session.commit()


@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "base"), [("arp", "/arp"), ("trainer", "/trainer")])
async def test_page_shows_the_pack_with_demo_label_and_no_teacher_name(
    session_factory: async_sessionmaker[AsyncSession], role: str, base: str
) -> None:
    await _seed_full(session_factory)
    res = await _get(base, await _user(role), session_factory)
    assert res.status_code == 200
    html = res.text
    assert 'id="cluster-pack"' in html
    assert get_message("ui_pack_title") in html
    assert escape(LIB.get(WITH_MOVE).label_hi) in html  # type: ignore[union-attr]
    assert get_message("ui_pack_move", move="").split(":")[0] in html
    assert 'id="cluster-pack-demo"' in html
    assert f'href="{base}/cluster-pack/print"' in html
    card = html.split('id="cluster-pack"')[1].split("</section>")[0]
    assert SECRET_NAME not in card  # the ARP digest lists teachers; the pack card never does


@pytest.mark.asyncio
async def test_arp_page_suppresses_a_small_cluster(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        who = await _teachers(session, N - 3)
        await _report(session, who, WITH_MOVE)
        await session.commit()
    res = await _get("/arp", await _user("arp"), session_factory)
    assert 'id="cluster-pack-suppressed"' in res.text
    assert escape(SUPPRESSION_MESSAGE) in res.text
    assert (
        LIB.get(WITH_MOVE).label_hi
        not in res.text.split('id="cluster-pack"')[1].split("</section>")[0]
    )  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_arp_page_empty_state(session_factory: async_sessionmaker[AsyncSession]) -> None:
    res = await _get("/arp", await _user("arp"), session_factory)
    assert 'id="cluster-pack-empty"' in res.text


@pytest.mark.asyncio
async def test_pack_with_no_qualifying_struggle_says_so(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        who = await _teachers(session, N)
        await _report(session, who, None, outcome="well")
        await _report(session, who[:2], WITH_MOVE)
        await session.commit()
    res = await _get("/arp", await _user("arp"), session_factory)
    assert 'id="cluster-pack-few"' in res.text
    assert 'id="cluster-pack-print"' not in res.text


@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "base"), [("arp", "/arp"), ("trainer", "/trainer")])
async def test_print_view_is_one_server_rendered_agenda_without_javascript(
    session_factory: async_sessionmaker[AsyncSession], role: str, base: str
) -> None:
    await _seed_full(session_factory)
    res = await _get(f"{base}/cluster-pack/print", await _user(role), session_factory)
    assert res.status_code == 200
    html = res.text
    assert "<script" not in html.lower()
    assert 'id="pack-agenda"' in html and html.count("<tr>") == 4
    minutes = settings.CLUSTER_PACK_AGENDA_MINUTES
    for m in minutes:
        assert get_message("ui_pack_minutes", m=m) in html
    assert get_message("ui_pack_agenda_plan") in html
    assert get_message("ui_pack_agenda_practise", move="").split("{")[0].split(":")[0] in html
    assert 'id="pack-print-demo"' in html
    assert escape(LIB.get(WITH_MOVE).tip_hi) in html  # type: ignore[union-attr]
    assert SECRET_NAME not in html
    assert res.headers["cache-control"] == "no-store"


@pytest.mark.asyncio
async def test_print_view_says_so_when_no_struggle_has_a_move(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        who = await _teachers(session, N)
        await _report(session, who, NO_MOVE)
        await session.commit()
    res = await _get("/arp/cluster-pack/print", await _user("arp"), session_factory)
    assert get_message("ui_pack_agenda_nomove") in res.text


@pytest.mark.asyncio
async def test_print_view_when_suppressed_shows_no_agenda(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        who = await _teachers(session, 3)
        await _report(session, who, WITH_MOVE)
        await session.commit()
    res = await _get("/arp/cluster-pack/print", await _user("arp"), session_factory)
    assert 'id="pack-print-suppressed"' in res.text and 'id="pack-agenda"' not in res.text


@pytest.mark.asyncio
async def test_role_guard_on_the_print_views(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    teacher = await _user("teacher")
    assert (await _get("/arp/cluster-pack/print", teacher, session_factory)).status_code == 403
    assert (await _get("/trainer/cluster-pack/print", teacher, session_factory)).status_code == 403
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        assert (await client.get("/arp/cluster-pack/print")).status_code == 401


@pytest.mark.asyncio
async def test_flag_off_no_card_and_the_print_view_is_not_found(
    session_factory: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> None:
    await _seed_full(session_factory)
    monkeypatch.setattr(settings, "CLUSTER_PACK_ENABLED", False)
    monkeypatch.setattr(settings, "DEMO_MODE", False)
    res = await _get("/arp", await _user("arp"), session_factory)
    assert res.status_code == 200 and 'id="cluster-pack"' not in res.text
    res = await _get("/trainer", await _user("trainer"), session_factory)
    assert 'id="cluster-pack"' not in res.text
    assert (
        await _get("/arp/cluster-pack/print", await _user("arp"), session_factory)
    ).status_code == 404
    monkeypatch.setattr(settings, "CLUSTER_PACK_ENABLED", True)
    assert 'id="cluster-pack"' in (await _get("/arp", await _user("arp"), session_factory)).text


@pytest.mark.asyncio
async def test_pages_in_english(session_factory: async_sessionmaker[AsyncSession]) -> None:
    from backend.app.web.ui_lang import LANG_COOKIE_NAME

    await _seed_full(session_factory)
    cookies = {LANG_COOKIE_NAME: "en"}
    res = await _get("/arp", await _user("arp"), session_factory, cookies)
    pr = await _get("/arp/cluster-pack/print", await _user("arp"), session_factory, cookies)
    assert "Cluster meeting pack" in res.text
    assert 'lang="en"' in pr.text and "Cluster meeting: agenda" in pr.text


def _card(html: str) -> str:
    return html.split('id="cluster-pack"')[1].split("</section>")[0]


@pytest.mark.asyncio
@pytest.mark.parametrize("lang", ["hi", "en"])
async def test_rows_say_children_get_stuck_as_teachers_reported(
    session_factory: async_sessionmaker[AsyncSession], lang: str
) -> None:
    await _seed_full(session_factory)
    token = set_ui_lang(lang)  # for get_message below; the page reads the cookie
    cookies = {"abhyas_lang": lang}
    try:
        res = await _get("/arp", await _user("arp"), session_factory, cookies)
        card = _card(res.text)
        struggle = LIB.get(WITH_MOVE)
        assert struggle is not None
        label = struggle.label_en if lang == "en" else struggle.label_hi
        row = get_message("ui_pack_row", label=label, n=N + 4)
        assert escape(row) in card
        assert "*" not in card
        if lang == "hi":
            assert "बच्चे अटकते हैं" in row and "शिक्षकों ने बताया" in row
    finally:
        reset_ui_lang(token)


@pytest.mark.asyncio
@pytest.mark.parametrize("lang", ["hi", "en"])
async def test_print_agenda_lines_are_catalog_strings_without_asterisks(
    session_factory: async_sessionmaker[AsyncSession], lang: str
) -> None:
    await _seed_full(session_factory)
    token = set_ui_lang(lang)
    try:
        res = await _get(
            "/arp/cluster-pack/print", await _user("arp"), session_factory, {"abhyas_lang": lang}
        )
        html = res.text
        assert "*" not in html
        share = get_message("ui_pack_agenda_share", items="").split("{")[0].split(":")[0]
        assert escape(share) in html
        assert get_message("ui_pack_agenda_plan") in html
    finally:
        reset_ui_lang(token)


@pytest.mark.asyncio
@pytest.mark.parametrize(("count", "suppressed"), [(N - 1, True), (N, False)])
async def test_pack_is_suppressed_at_nine_and_shown_at_ten(
    session_factory: async_sessionmaker[AsyncSession], count: int, suppressed: bool
) -> None:
    assert N == 10
    async with session_factory() as session:
        who = await _teachers(session, count)
        await _report(session, who, WITH_MOVE)
        await session.commit()
    res = await _get("/arp", await _user("arp"), session_factory)
    card = _card(res.text)
    label = escape(LIB.get(WITH_MOVE).label_hi)  # type: ignore[union-attr]
    assert ('id="cluster-pack-suppressed"' in card) is suppressed
    assert (label in card) is (not suppressed)
