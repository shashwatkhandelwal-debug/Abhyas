"""Adaptive next practice: fixed histories through the pure chooser and the real SessionService."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from test_class_checkin import Teacher, alltext, ids
from test_followup import Clock

from backend.app.channels.whatsapp.buttons import plan_buttons
from backend.app.class_profile import adaptive, followup
from backend.app.class_profile.adaptive import CheckinSignal, FollowupSignal, choose_next
from backend.app.config import settings
from backend.app.core.messages import get_message, reset_ui_lang, set_ui_lang
from backend.app.db.models import ClassCheckin
from backend.app.sessions.path import MovePathEntry
from backend.app.sessions.state_machine import SessionStateEnum
from backend.app.sessions.titles import move_title

NOW = datetime(2026, 10, 30, 5, 0, tzinfo=UTC)
PATH = [
    "NUM_PLACE_VALUE_BUNDLES",
    "NUM_SUB_REGROUP_BUNDLES",
    "NUM_ADD_CARRY_BUNDLES",
    "LIT_MATRA_BLENDING",
]
SUB, ADD, MATRA = "NUM_SUB_REGROUP", "NUM_ADD_CARRY", "LIT_MATRA_DROP"
DASHES = ("—", "–")
DAY = timedelta(days=1)


def ci(outcome: str, *sids: str, days: float = 2) -> CheckinSignal:
    return CheckinSignal(outcome, list(sids), NOW - days * DAY)


def fu(sid: str, outcome: str, days: float = 1) -> FollowupSignal:
    return FollowupSignal(sid, outcome, NOW - days * DAY)


def pick(
    candidates: list[str] | None = None,
    checkins: list[CheckinSignal] | None = None,
    followups: list[FollowupSignal] | None = None,
    band: str | None = "6-10",
) -> adaptive.Choice | None:
    return choose_next(
        PATH[1:] if candidates is None else candidates,  # she just finished the first move
        checkins=checkins or [],
        followups=followups or [],
        experience_band=band,
        now=NOW,
    )


@pytest.fixture(autouse=True)
def flags(monkeypatch: pytest.MonkeyPatch) -> Clock:
    monkeypatch.setattr(settings, "ADAPTIVE_PATH_ENABLED", True)
    monkeypatch.setattr(settings, "DEMO_MODE", False)
    clock = Clock(NOW)
    monkeypatch.setattr(followup, "utcnow", clock)
    return clock


@pytest.fixture(params=["hi", "en"])
def lang(request: pytest.FixtureRequest) -> Iterator[str]:
    token = set_ui_lang(request.param)
    yield request.param
    reset_ui_lang(token)


# ── the pure chooser ─────────────────────────────────────────────────────────────────────────
def test_no_history_keeps_the_old_order() -> None:
    assert pick() is None
    assert pick(band="0-1") is None  # even a new teacher: no history, no change


def test_a_most_struggled_checkin_moves_that_move_first() -> None:
    c = pick(checkins=[ci("most", MATRA)])
    assert c is not None and c.move_id == "LIT_MATRA_BLENDING"
    assert (c.signal, c.struggle_id) == ("most", MATRA)


def test_most_weighs_more_than_some_and_a_tie_keeps_her_path_order() -> None:
    c = pick(checkins=[ci("some", ADD), ci("most", MATRA)])
    assert c is not None and c.move_id == "LIT_MATRA_BLENDING"
    tie = pick(checkins=[ci("some", ADD), ci("some", MATRA)])
    assert tie is not None and tie.move_id == "NUM_ADD_CARRY_BUNDLES"  # earlier in her path


def test_went_well_checkins_and_old_history_are_ignored() -> None:
    assert pick(checkins=[ci("well", MATRA)]) is None
    old = ci("most", MATRA, days=settings.ADAPTIVE_HISTORY_DAYS + 1)
    assert pick(checkins=[old]) is None


def test_still_stuck_raises_that_struggles_move() -> None:
    c = pick(followups=[fu(MATRA, "stuck")])
    assert c is not None and (c.move_id, c.signal) == ("LIT_MATRA_BLENDING", "stuck")


def test_stuck_adds_to_a_check_in_and_can_overtake_it() -> None:
    plain = pick(checkins=[ci("most", ADD), ci("some", MATRA), ci("some", MATRA)])
    assert plain is not None and plain.move_id == "NUM_ADD_CARRY_BUNDLES"
    raised = pick(
        checkins=[ci("most", ADD), ci("some", MATRA), ci("some", MATRA)],
        followups=[fu(MATRA, "stuck")],
    )
    assert raised is not None and raised.move_id == "LIT_MATRA_BLENDING"


def test_worked_lowers_that_move() -> None:
    both = [ci("most", SUB), ci("most", ADD)]
    base = pick(checkins=both)  # a tie keeps her path order: sub first
    assert base is not None and base.move_id == "NUM_SUB_REGROUP_BUNDLES"
    lowered = pick(checkins=both, followups=[fu(SUB, "worked")])
    assert lowered is not None and lowered.move_id == "NUM_ADD_CARRY_BUNDLES"
    only = pick(followups=[fu(SUB, "worked")])  # lowered first move: the next one comes first
    assert only is not None and (only.move_id, only.signal) == ("NUM_ADD_CARRY_BUNDLES", "worked")


def test_a_new_teacher_gets_the_first_basic_practice_before_a_single_class_signal() -> None:
    new = pick(checkins=[ci("most", MATRA)], band="0-1")
    assert new is not None and (new.move_id, new.signal) == ("NUM_SUB_REGROUP_BUNDLES", "new")
    experienced = pick(checkins=[ci("most", MATRA)], band="10+")
    assert experienced is not None and experienced.move_id == "LIT_MATRA_BLENDING"


def test_a_new_teacher_with_a_strong_signal_still_gets_it_when_it_outweighs_the_bonus() -> None:
    c = pick(checkins=[ci("most", MATRA), ci("most", MATRA)], band="0-1")
    assert c is not None and c.move_id == "LIT_MATRA_BLENDING"


def test_two_teachers_with_different_histories_get_different_practices() -> None:
    a = pick(checkins=[ci("most", MATRA)])
    b = pick(checkins=[ci("most", ADD)])
    assert a is not None and b is not None and a.move_id != b.move_id


def test_the_chooser_only_returns_moves_it_was_given() -> None:
    assert pick(candidates=["NUM_ADD_CARRY_BUNDLES"], checkins=[ci("most", MATRA)]) is None
    assert pick(candidates=[], checkins=[ci("most", MATRA)]) is None
    c = pick(checkins=[ci("most", MATRA), ci("most", SUB), ci("some", ADD)])
    assert c is not None and c.move_id in PATH[1:]


def test_a_struggle_with_no_move_never_changes_the_order() -> None:
    assert pick(checkins=[ci("most", "NUM_COUNTING")]) is None


# ── the reason line ─────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("signal", ["most", "some", "stuck", "worked", "new"])
def test_every_reason_is_one_catalog_line_without_dashes(lang: str, signal: str) -> None:
    text = adaptive.reason_text(adaptive.Choice("LIT_MATRA_BLENDING", signal, MATRA))
    prefix = "क्यों अभी यह" if lang == "hi" else "Why this next"
    assert text.startswith(prefix) and "\n" not in text
    assert not any(d in text for d in DASHES) and "{" not in text


# ── through the real SessionService ────────────────────────────────────────────────────────
async def teacher_with_path(band: str | None = "6-10", profile: str = "demo3") -> Teacher:
    t = await Teacher(profile, "f").setup()
    ctx = await t.ctx()
    ctx.current_move_id = PATH[0]
    ctx.current_state = SessionStateEnum.DONE
    ctx.experience_band = band
    await t.service._sync_context_to_db(ctx, t.teacher_id)
    t.repo._move_paths = [m for m in t.repo._move_paths if m.teacher_id != t.teacher_id]
    await t.repo.record_move_path(
        t.teacher_id, [MovePathEntry(i + 1, m, "x") for i, m in enumerate(PATH)]
    )
    return t


def add_checkin(t: Teacher, outcome: str, sid: str, days: float = 2) -> None:
    t.repo._class_checkins.append(
        ClassCheckin(
            id=__import__("uuid").uuid4(),
            teacher_id=t.teacher_id,
            module_id="x",
            outcome=outcome,
            struggle_ids=[sid],
            created_at=NOW - days * DAY,
        )
    )


@pytest.mark.asyncio
async def test_service_no_history_is_exactly_the_old_behaviour(lang: str) -> None:
    t = await teacher_with_path()
    out = await t.tap("btn_next_move")
    ctx = await t.ctx()
    assert ctx.current_move_id == PATH[0]  # the old behaviour: same move restarts
    assert "क्यों अभी यह" not in alltext(out) and "Why this next" not in alltext(out)


@pytest.mark.asyncio
async def test_service_most_struggled_opens_that_practice_with_the_reason(lang: str) -> None:
    t = await teacher_with_path()
    add_checkin(t, "most", MATRA)
    out = await t.tap("btn_next_move")
    ctx = await t.ctx()
    assert ctx.current_move_id == "LIT_MATRA_BLENDING"
    reason = adaptive.reason_text(adaptive.Choice("LIT_MATRA_BLENDING", "most", MATRA))
    assert reason in out[0].text_hi  # inside the existing learn message, not a new bubble
    assert len(out) <= 2


@pytest.mark.asyncio
async def test_service_week_done_names_the_chosen_practice_and_why(lang: str) -> None:
    t = await teacher_with_path()
    add_checkin(t, "most", ADD)
    ctx = await t.ctx()
    msgs = await t.service._week_done_messages(ctx, t.teacher_id, 2)
    text = alltext(msgs)
    assert move_title("NUM_ADD_CARRY_BUNDLES") in text
    assert adaptive.reason_text(adaptive.Choice("NUM_ADD_CARRY_BUNDLES", "most", ADD)) in text
    assert len(msgs) == 1


@pytest.mark.asyncio
async def test_service_two_teachers_get_different_next_practices() -> None:
    a = await teacher_with_path()
    b = await teacher_with_path()
    add_checkin(a, "most", MATRA)
    add_checkin(b, "most", ADD)
    await a.tap("btn_next_move")
    await b.tap("btn_next_move")
    assert (await a.ctx()).current_move_id != (await b.ctx()).current_move_id


@pytest.mark.asyncio
async def test_service_new_teacher_gets_the_basic_practice_first() -> None:
    t = await teacher_with_path(band="0-1")
    add_checkin(t, "most", MATRA)
    await t.tap("btn_next_move")
    assert (await t.ctx()).current_move_id == "NUM_SUB_REGROUP_BUNDLES"


@pytest.mark.asyncio
async def test_service_followup_outcomes_steer_the_choice() -> None:
    t = await teacher_with_path()
    t.repo._followups.append(
        __import__("backend.app.db.models", fromlist=["ClassFollowup"]).ClassFollowup(
            id=(fid := __import__("uuid").uuid4()),
            teacher_id=t.teacher_id,
            checkin_id=__import__("uuid").uuid4(),
            struggle_id=MATRA,
            due_date=date(2026, 10, 29),
            created_at=NOW - 2 * DAY,
        )
    )
    await t.repo.record_followup_outcome(t.teacher_id, fid, "stuck")
    t.repo._followup_outcomes[0].created_at = NOW - DAY
    await t.tap("btn_next_move")
    assert (await t.ctx()).current_move_id == "LIT_MATRA_BLENDING"


@pytest.mark.asyncio
async def test_service_flag_off_keeps_the_old_behaviour_exactly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "ADAPTIVE_PATH_ENABLED", False)
    t = await teacher_with_path()
    add_checkin(t, "most", MATRA)
    out = await t.tap("btn_next_move")
    assert (await t.ctx()).current_move_id == PATH[0]
    assert "क्यों अभी यह" not in alltext(out)
    ctx = await t.ctx()
    done = await t.service._week_done_messages(ctx, t.teacher_id, 2)
    assert "क्यों अभी यह" not in alltext(done) and "Why this next" not in alltext(done)


@pytest.mark.asyncio
async def test_service_never_removes_a_move_from_her_path() -> None:
    t = await teacher_with_path()
    add_checkin(t, "most", MATRA)
    await t.tap("btn_next_move")
    rows = await t.repo.get_move_path(t.teacher_id)
    assert [r.move_id for r in rows] == PATH


@pytest.mark.asyncio
async def test_demo_mode_turns_it_on_without_the_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "ADAPTIVE_PATH_ENABLED", False)
    monkeypatch.setattr(settings, "DEMO_MODE", True)
    assert adaptive.enabled()
    assert settings.model_fields["ADAPTIVE_PATH_ENABLED"].default is False


@pytest.mark.asyncio
async def test_whatsapp_caps_hold_on_the_week_done_message(lang: str) -> None:
    t = await teacher_with_path()
    add_checkin(t, "most", ADD)
    ctx = await t.ctx()
    (msg,) = await t.service._week_done_messages(ctx, t.teacher_id, 2)
    assert len(ids([msg])) <= 3 + 1  # next, progress and the check-in entry
    plan = plan_buttons(msg.buttons or [], has_audio=False)
    assert len(plan.reply_buttons) <= 3
    assert all(len(title) <= settings.WHATSAPP_BUTTON_TITLE_MAX for _, title in plan.reply_buttons)
    assert get_message("btn_next_move")  # the title key still resolves


_ = ZoneInfo  # the harness fixes the clock in UTC
