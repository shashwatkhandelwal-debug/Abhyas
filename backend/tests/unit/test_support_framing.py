# ruff: noqa: F811  (the ARP fixtures are reused by name from test_arp_digest)
"""Support, not monitoring: neutral ARP wording, the ARP's visit note to the teacher, no scores
for a teacher who has not opted in to sharing (ARP and trainer pages)."""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncGenerator, Iterator
from datetime import UTC, date, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from test_arp_digest import arp_app, arp_user  # noqa: F401
from test_class_checkin import Teacher, ids
from test_state_machine import FakeSessionRepository

from backend.app.auth.guards import get_current_user
from backend.app.class_profile import followup, visit_note
from backend.app.config import settings
from backend.app.core.messages import get_message, reset_ui_lang, set_ui_lang
from backend.app.db.base import Base
from backend.app.db.models import (
    AppUser,
    ClassVisitObservation,
    Cluster,
    RehearsalScore,
    Scene,
    Turn,
)
from backend.app.db.models import Teacher as TeacherRow
from backend.app.db.session import get_db_session
from backend.app.main import app
from backend.app.reports.arp_digest import ARPDigestData, SuggestedVisit, TeacherDigestRow

DASHES = ("—", "–")
RED_BADGE = 'class="badge-help"'


@pytest.fixture(params=["hi", "en"])
def lang(request: pytest.FixtureRequest) -> Iterator[str]:
    token = set_ui_lang(request.param)
    yield request.param
    reset_ui_lang(token)


# (a) neutral support wording on the ARP page
def _digest() -> ARPDigestData:
    tid = str(uuid.uuid4())
    row = TeacherDigestRow(
        teacher_id=tid,
        name="सुमन शर्मा",
        school="प्रा.वि. कल्यानपुर",
        move_id="NUM_SUB_REGROUP_BUNDLES",
        move_title="हासिल वाला घटाव",
        step_reached="REHEARSE",
        max_evidence_level=2,
        rubric_dots=[],
        needs_help=True,
        avg_score=0.5,
    )
    return ARPDigestData(
        cluster_id="KNP-C01",
        cluster_name="कल्याणपुर संकुल",
        selected_week_start=date(2026, 10, 19),
        available_weeks=[date(2026, 10, 19)],
        total_teachers=1,
        active_teachers_count=1,
        completed_loops_count=0,
        moves_practised_count=1,
        consenting_teachers=[row],
        non_consenting_count=0,
        suggested_visits=[
            SuggestedVisit(
                teacher_id=tid,
                name="सुमन शर्मा",
                school="प्रा.वि. कल्यानपुर",
                move_id="NUM_SUB_REGROUP_BUNDLES",
                move_title="हासिल वाला घटाव",
                avg_score=0.5,
                peer_checklist=[],
            )
        ],
        escalated_questions=[],
    )


async def arp_html(
    app_: Any, user: AppUser, monkeypatch: pytest.MonkeyPatch, cookie_lang: str
) -> str:
    import backend.app.web.arp as arp_module

    app_.dependency_overrides[get_current_user] = lambda: user
    app_.dependency_overrides[get_db_session] = lambda: AsyncMock(spec=AsyncSession)
    monkeypatch.setattr(arp_module, "build_arp_digest", AsyncMock(return_value=_digest()))
    monkeypatch.setattr(arp_module, "module_progress_summary", AsyncMock(return_value=[]))
    async with AsyncClient(
        transport=ASGITransport(app=app_), base_url="http://testserver"
    ) as client:
        res = await client.get("/arp", cookies={"abhyas_lang": cookie_lang})
    assert res.status_code == 200
    return res.text


@pytest.mark.asyncio
async def test_support_framing_replaces_the_red_label_and_adds_the_line(
    arp_app: Any, arp_user: AppUser, monkeypatch: pytest.MonkeyPatch, lang: str
) -> None:
    monkeypatch.setattr(settings, "DEMO_MODE", False)
    monkeypatch.setattr(settings, "SUPPORT_FRAMING_ENABLED", True)
    html = await arp_html(arp_app, arp_user, monkeypatch, lang)
    assert RED_BADGE not in html
    assert 'class="badge-support"' in html
    assert get_message("ui_arp_practise_together", lang=lang) in html
    line = get_message("ui_support_line", lang=lang)
    assert html.count(line) >= 2  # above the teacher table and above the visit list
    assert get_message("ui_arp_needs_help", lang=lang) not in html


@pytest.mark.asyncio
async def test_flag_off_the_old_wording_is_unchanged(
    arp_app: Any, arp_user: AppUser, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "DEMO_MODE", False)
    monkeypatch.setattr(settings, "SUPPORT_FRAMING_ENABLED", False)
    html = await arp_html(arp_app, arp_user, monkeypatch, "hi")
    assert RED_BADGE in html and get_message("ui_arp_needs_help", lang="hi") in html
    assert 'class="badge-support"' not in html and "arp-support-line" not in html


def test_support_texts_exist_in_both_languages_without_dashes() -> None:
    for code in ("hi", "en"):
        for key in ("ui_arp_practise_together", "ui_support_line"):
            assert not any(d in get_message(key, lang=code) for d in DASHES)
    assert get_message("ui_arp_practise_together", lang="hi") == "साथ में अभ्यास करें"
    assert get_message("ui_arp_practise_together", lang="en") == "Practise together"
    assert get_message("ui_support_line", lang="hi") == (
        "ये शिक्षक अपनी मर्ज़ी से आपके साथ अंक साझा करते हैं। यह मूल्यांकन नहीं, सहयोग के लिए है।"
    )


# (b) the ARP's observation, shown to the teacher as a note
@pytest.fixture
def repo_hooks(monkeypatch: pytest.MonkeyPatch) -> None:
    async def last_button_time(
        self: FakeSessionRepository, teacher_id: Any, button_ids: tuple[str, ...]
    ) -> datetime | None:
        sent = [t for t, ids_ in getattr(self, "_sent", []) if set(ids_) & set(button_ids)]
        return max(sent, default=None)

    async def latest_visit(
        self: FakeSessionRepository, teacher_id: Any, since: datetime
    ) -> ClassVisitObservation | None:
        rows = [
            v
            for v in getattr(self, "_visits", [])
            if v.teacher_id == teacher_id and v.created_at >= since
        ]
        return max(rows, key=lambda v: v.created_at, default=None)

    monkeypatch.setattr(FakeSessionRepository, "last_outbound_button_time", last_button_time)
    monkeypatch.setattr(FakeSessionRepository, "latest_visit_observation", latest_visit)
    monkeypatch.setattr(settings, "DEMO_MODE", False)
    monkeypatch.setattr(settings, "OBSERVATION_TO_TEACHER_ENABLED", True)


def add_visit(
    t: Teacher,
    created: datetime,
    *,
    talk: tuple[str, ...] = ("named_child", "why_how"),
    seen: bool = False,
    step: str = "ask_named",
    struggle: str | None = None,
) -> None:
    rows: list[Any] = getattr(t.repo, "_visits", [])
    rows.append(
        ClassVisitObservation(
            id=uuid.uuid4(),
            teacher_id=t.teacher_id,
            talk_moves=list(talk),
            practice_seen=seen,
            struggle_id=struggle,
            next_step=step,
            observed_on=created.date(),
            created_at=created,
        )
    )
    t.repo._visits = rows  # type: ignore[attr-defined]


def deliver(t: Teacher, when: datetime, out: list[Any]) -> None:
    sent: list[Any] = getattr(t.repo, "_sent", [])
    sent.extend((when, [b.id for b in m.buttons]) for m in out)
    t.repo._sent = sent  # type: ignore[attr-defined]


def now() -> datetime:
    return datetime.now(UTC)


@pytest.mark.asyncio
async def test_the_note_is_framed_as_seen_and_try_with_one_ok_button(
    repo_hooks: None, lang: str
) -> None:
    t = await Teacher("demo3", "f").setup()
    assert await t.service.offer_visit_note(t.teacher_id) == []  # nothing saved yet
    add_visit(t, now(), seen=True, struggle="NUM_SUB_REGROUP", step="ask_why")
    out = await t.service.offer_visit_note(t.teacher_id)
    assert len(out) == 1 and ids(out) == [visit_note.BTN_OK]
    body = out[0].text_hi or ""
    seen_text = (
        f"{get_message('ui_visit_talk_named_child')}; {get_message('ui_visit_talk_why_how')}; "
    )
    assert seen_text in body and get_message("ui_visit_next_ask_why") in body
    assert body.startswith(get_message("obs_note", worked="x", step="y").split("x")[0])
    # never a rating: no score, no level, no number at all
    assert not any(ch.isdigit() for ch in body)
    assert not any(w in body.lower() for w in ("score", "rating", "level", "अंक", "स्तर"))
    assert not any(d in body for d in DASHES)
    assert (out[0].buttons[0].title_hi) == get_message(visit_note.BTN_OK)


@pytest.mark.asyncio
async def test_hindi_framing_text_is_exact(repo_hooks: None) -> None:
    t = await Teacher("demo3", "f").setup()
    add_visit(t, now(), talk=("named_child",), step="ask_named")
    out = await t.service.offer_visit_note(t.teacher_id)
    assert out[0].text_hi == (
        "आपके ARP ने देखा: किसी बच्चे को नाम लेकर बुलाया। एक बात आज़माएँ: अगली बार नाम लेकर पूछें।"
    )


@pytest.mark.asyncio
async def test_shown_once_until_a_newer_observation(repo_hooks: None) -> None:
    t = await Teacher("demo3", "f").setup()
    first = now() - timedelta(days=2)
    add_visit(t, first)
    out = await t.service.offer_visit_note(t.teacher_id)
    deliver(t, now() - timedelta(days=1), out)
    assert await t.service.offer_visit_note(t.teacher_id) == []
    add_visit(t, now(), talk=("think_time",), step="wait_time")
    again = await t.service.offer_visit_note(t.teacher_id)
    assert get_message("ui_visit_talk_think_time") in (again[0].text_hi or "")


@pytest.mark.asyncio
async def test_old_observations_are_not_shown(repo_hooks: None) -> None:
    t = await Teacher("demo3", "f").setup()
    add_visit(t, now() - timedelta(days=settings.OBSERVATION_WINDOW_DAYS + 5))
    assert await t.service.offer_visit_note(t.teacher_id) == []


@pytest.mark.asyncio
async def test_ok_acknowledges_and_writes_nothing_and_feeds_no_score(repo_hooks: None) -> None:
    t = await Teacher("demo3", "f").setup()
    add_visit(t, now())
    before = (
        len(t.repo._evidence),
        len(t.repo._rehearsal_scores),
        len(t.repo._explain_scores),
        len(t.repo._class_checkins),
    )
    out = await t.service.offer_visit_note(t.teacher_id)
    ack = await t.tap(visit_note.BTN_OK)
    assert ack[0].text_hi == get_message("obs_ok_ack")
    after = (
        len(t.repo._evidence),
        len(t.repo._rehearsal_scores),
        len(t.repo._explain_scores),
        len(t.repo._class_checkins),
    )
    assert before == after and out


@pytest.mark.asyncio
async def test_flag_off_no_note_and_the_button_is_not_handled(
    repo_hooks: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    t = await Teacher("demo3", "f").setup()
    add_visit(t, now())
    monkeypatch.setattr(settings, "OBSERVATION_TO_TEACHER_ENABLED", False)
    assert await t.service.offer_visit_note(t.teacher_id) == []
    out = await t.tap(visit_note.BTN_OK)
    assert not out or out[0].text_hi != get_message("obs_ok_ack")


def test_note_texts_in_both_languages_and_title_fits() -> None:
    for code in ("hi", "en"):
        for key in ("obs_note", "obs_note_no_step", "obs_ok_ack", "btn_obs_ok", "obs_worked_none"):
            text_ = get_message(key, lang=code, worked="a", step="b")
            assert text_ and not any(d in text_ for d in DASHES), key
        assert len(get_message("btn_obs_ok", lang=code)) <= settings.WHATSAPP_BUTTON_TITLE_MAX
    _ = followup


# (c) no per-teacher score for a teacher who has not opted in, on the ARP or trainer pages
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


@needs_db
@pytest.mark.asyncio
async def test_a_teacher_who_has_not_opted_in_shows_no_score_to_arp_or_trainer(
    factory: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "DEMO_MODE", True)
    tag = uuid.uuid4().hex[:8]
    district, cluster = f"SupDist-{tag}", f"SUP-{tag}"
    secret = f"गोपनीय_{tag}"
    async with factory() as session:
        session.add(Cluster(id=cluster, name="संकुल", district=district))
        await session.flush()
        arp = AppUser(
            id=uuid.uuid4(),
            username=f"arp.sup.{tag}",
            password_hash="x",
            role="arp",
            cluster_id=cluster,
            district=district,
        )
        trainer = AppUser(
            id=uuid.uuid4(),
            username=f"trainer.sup.{tag}",
            password_hash="x",
            role="trainer",
            district=district,
        )
        session.add_all([arp, trainer])
        shared = []
        for i in range(10):
            row = TeacherRow(
                id=uuid.uuid4(),
                name=f"साझा_{tag}_{i}",
                phone_hash=f"h{uuid.uuid4().hex}",
                cluster_id=cluster,
                district=district,
                consent_share_scores=True,
                is_demo=False,
            )
            session.add(row)
            shared.append(row)
        hidden = TeacherRow(
            id=uuid.uuid4(),
            name=secret,
            phone_hash=f"h{uuid.uuid4().hex}",
            cluster_id=cluster,
            district=district,
            consent_share_scores=False,
            is_demo=False,
        )
        session.add(hidden)
        await session.flush()
        move = "NUM_SUB_REGROUP_BUNDLES"
        session.add(
            RehearsalScore(
                teacher_id=hidden.id, move_id=move, scores={"crit_x": 0, "crit_y": 0}, evidence={}
            )
        )
        for t in [*shared, hidden]:
            scene = Scene(
                id=uuid.uuid4(),
                teacher_id=t.id,
                move_id=move,
                engine_state={"one_on_one": False},
                status="ended",
                started_at=datetime.now(UTC) - timedelta(days=1),
            )
            session.add(scene)
            await session.flush()
            session.add(
                Turn(
                    id=uuid.uuid4(),
                    teacher_id=t.id,
                    scene_id=scene.id,
                    idx=1,
                    role="teacher",
                    acts=["tell_answer"],
                    addressed_child="all",
                )
            )
        await session.commit()

    async def db() -> AsyncGenerator[AsyncSession, None]:
        async with factory() as s:
            yield s

    current: dict[str, AppUser] = {"u": arp}

    async def whoami() -> AppUser:
        return current["u"]

    app.dependency_overrides[get_db_session] = db
    app.dependency_overrides[get_current_user] = whoami
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            page = await client.get("/arp")
            assert page.status_code == 200 and secret not in page.text
            assert 'id="arp-support-line"' in page.text  # demo mode: support wording is on
            current["u"] = trainer
            for path in ("/trainer", "/trainer/export.csv", f"/trainer/move/{move}"):
                res = await client.get(path)
                assert res.status_code == 200, path
                assert secret not in res.text, path
            dash = await client.get("/trainer")
            # the 10 sharing teachers are counted; the one who has not opted in is not the 11th
            assert "10/10" in dash.text and "11/11" not in dash.text
    finally:
        app.dependency_overrides.clear()
        async with factory() as session:
            await session.execute(delete(Turn).where(Turn.teacher_id == hidden.id))
            await session.commit()
