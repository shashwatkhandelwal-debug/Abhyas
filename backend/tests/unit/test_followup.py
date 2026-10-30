"""The follow-up loop ("How did yesterday's practice go?") through the real SessionService (mocks).

Every path, flag off and on, Hindi and English, she and he, demo2 and demo3 profiles, the due-date
rule with a fixed clock (including a Sunday), double taps, the WhatsApp button caps and the
tomorrow's-focus builder. No LLM is involved anywhere in the flow.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from test_class_checkin import (  # noqa: F401
    Teacher,
    alltext,
    ids,
    open_module,
    struggle_button,
)

from backend.app.channels.whatsapp.buttons import plan_buttons
from backend.app.class_profile import checkin_flow, followup
from backend.app.class_profile.checkin_flow import struggle_label
from backend.app.class_profile.library import StruggleLibrary, load_library
from backend.app.config import settings
from backend.app.core.messages import FEMININE_MARKERS, get_message, reset_ui_lang, set_ui_lang
from backend.app.sessions.state_machine import SessionContext

IST = ZoneInfo("Asia/Kolkata")
LIB = load_library()
MAPPED = LIB.get("NUM_SUB_REGROUP")
NO_MOVE = LIB.get("NUM_COUNTING")
assert MAPPED is not None and NO_MOVE is not None
FRIDAY = date(2026, 10, 30)
DASHES = ("—", "–")


def at(day: date, hour: int = 10) -> datetime:
    return datetime(day.year, day.month, day.day, hour, 0, tzinfo=IST).astimezone(UTC)


class Clock:
    def __init__(self, moment: datetime) -> None:
        self.moment = moment

    def __call__(self) -> datetime:
        return self.moment


@pytest.fixture(autouse=True)
def flags(monkeypatch: pytest.MonkeyPatch) -> Clock:
    monkeypatch.setattr(settings, "CLASS_CHECKIN_ENABLED", True)
    monkeypatch.setattr(settings, "FOLLOWUP_ENABLED", True)
    monkeypatch.setattr(settings, "LEVEL_SORTER_ENABLED", True)
    monkeypatch.setattr(settings, "DEMO_MODE", False)
    clock = Clock(at(FRIDAY))
    monkeypatch.setattr(followup, "utcnow", clock)
    return clock


@pytest.fixture(params=["hi", "en"])
def lang(request: pytest.FixtureRequest) -> Iterator[str]:
    token = set_ui_lang(request.param)
    yield request.param
    reset_ui_lang(token)


async def check_in(t: Teacher, struggle_id: str, outcome: str = "btn_chk_most") -> None:
    s = LIB.get(struggle_id)
    assert s is not None and s.move_id is not None or struggle_id == "NUM_COUNTING"
    module = next(m.id for m in checkin_flow.modules(LIB) if struggle_id in m.struggle_ids)
    await open_module(t, module)
    await t.tap(outcome)
    await t.tap(struggle_button(struggle_id))


async def due_and_offered(t: Teacher, clock: Clock, struggle_id: str = "NUM_SUB_REGROUP") -> None:
    await check_in(t, struggle_id)
    clock.moment = at(FRIDAY + timedelta(days=1))  # Saturday is a school day
    out = await t.service.offer_followup(t.teacher_id)
    assert ids(out) == [followup.BTN_WORKED, followup.BTN_STUCK, followup.BTN_CANT]


def stored_outcomes(t: Teacher) -> list[tuple[str, str | None]]:
    return [(o.outcome, o.reason) for o in t.repo._followup_outcomes]


# ── the due-date rule (fixed clock) ──────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    ("today", "due"),
    [
        (date(2026, 10, 26), date(2026, 10, 27)),  # Monday -> Tuesday
        (date(2026, 10, 30), date(2026, 10, 31)),  # Friday -> Saturday (a school day)
        (date(2026, 10, 31), date(2026, 11, 2)),  # Saturday -> Monday
        (date(2026, 11, 1), date(2026, 11, 2)),  # Sunday -> Monday
    ],
)
def test_next_school_day_is_monday_to_saturday(today: date, due: date) -> None:
    assert followup.next_school_day(today) == due
    assert due.weekday() in settings.FOLLOWUP_SCHOOL_DAYS


def test_due_is_on_or_after_the_day() -> None:
    due = date(2026, 11, 2)
    assert not followup.is_due(due, date(2026, 11, 1))
    assert followup.is_due(due, due)
    assert followup.is_due(due, date(2026, 11, 3))


def test_due_date_uses_the_indian_calendar_day() -> None:
    late_friday = datetime(2026, 10, 30, 20, 0, tzinfo=UTC)  # 01:30 Saturday in India
    assert followup.due_date_for(late_friday) == date(2026, 11, 2)


# ── storing the follow-up ────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_a_check_in_with_a_struggle_stores_one_follow_up_due_next_school_day(
    lang: str,
) -> None:
    t = await Teacher("demo3", "f").setup()
    await check_in(t, "NUM_SUB_REGROUP")
    [row] = t.repo._followups
    [chk] = t.stored()
    assert (row.teacher_id, row.checkin_id, row.struggle_id) == (
        t.teacher_id,
        chk.id,
        "NUM_SUB_REGROUP",
    )
    assert row.due_date == date(2026, 10, 31)
    assert row.offered_at is None


@pytest.mark.asyncio
async def test_a_sunday_check_in_is_due_on_monday(flags: Clock) -> None:
    flags.moment = at(date(2026, 11, 1))
    t = await Teacher("demo3", "f").setup()
    await check_in(t, "NUM_SUB_REGROUP", "btn_chk_some")
    assert [f.due_date for f in t.repo._followups] == [date(2026, 11, 2)]


@pytest.mark.asyncio
async def test_went_well_stores_no_follow_up(lang: str) -> None:
    t = await Teacher("demo3", "f").setup()
    await open_module(t, "NUM_ADD_CARRY_BUNDLES")
    await t.tap("btn_chk_well")
    assert t.stored() and t.repo._followups == []


@pytest.mark.asyncio
async def test_flag_off_stores_nothing_offers_nothing_and_ignores_taps(
    monkeypatch: pytest.MonkeyPatch, flags: Clock
) -> None:
    t = await Teacher("demo3", "f").setup()
    await due_and_offered(t, flags)  # on: a follow-up exists and was offered
    monkeypatch.setattr(settings, "FOLLOWUP_ENABLED", False)
    assert await t.service.offer_followup(t.teacher_id) == []
    await t.tap(followup.BTN_WORKED)
    assert stored_outcomes(t) == []
    t2 = await Teacher("demo3", "f").setup()
    await check_in(t2, "NUM_SUB_REGROUP")
    assert t2.repo._followups == []


@pytest.mark.asyncio
async def test_demo_mode_turns_it_on_without_the_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "FOLLOWUP_ENABLED", False)
    monkeypatch.setattr(settings, "DEMO_MODE", True)
    t = await Teacher("demo3", "f").setup()
    await check_in(t, "NUM_SUB_REGROUP")
    assert len(t.repo._followups) == 1
    assert settings.model_fields["FOLLOWUP_ENABLED"].default is False


# ── the offer ────────────────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_not_offered_before_the_due_day_then_offered_once(lang: str, flags: Clock) -> None:
    t = await Teacher("demo3", "f").setup()
    await check_in(t, "NUM_SUB_REGROUP")
    assert await t.service.offer_followup(t.teacher_id) == []  # the same day
    flags.moment = at(FRIDAY + timedelta(days=1))
    out = await t.service.offer_followup(t.teacher_id)
    assert ids(out) == [followup.BTN_WORKED, followup.BTN_STUCK, followup.BTN_CANT]
    expected = "कल का अभ्यास कैसा रहा?" if lang == "hi" else "How did yesterday's practice go?"
    assert expected in alltext(out)
    assert await t.service.offer_followup(t.teacher_id) == []  # opening again does not repeat it


@pytest.mark.asyncio
async def test_a_follow_up_older_than_the_limit_is_not_offered(flags: Clock) -> None:
    t = await Teacher("demo3", "f").setup()
    await check_in(t, "NUM_SUB_REGROUP")
    flags.moment = at(FRIDAY + timedelta(days=2 + settings.FOLLOWUP_MAX_AGE_DAYS))
    assert await t.service.offer_followup(t.teacher_id) == []


@pytest.mark.asyncio
async def test_not_offered_while_she_is_inside_another_screen(flags: Clock) -> None:
    t = await Teacher("demo3", "f").setup()
    await check_in(t, "NUM_SUB_REGROUP")
    flags.moment = at(FRIDAY + timedelta(days=1))
    await t.tap(checkin_flow.BTN_START)  # a check-in screen is open
    assert await t.service.offer_followup(t.teacher_id) == []


# ── worked ───────────────────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
@pytest.mark.parametrize("address_form", ["f", "m"])
@pytest.mark.parametrize("profile", ["demo2", "demo3"])
async def test_worked_acknowledges_stores_and_names_the_next_move(
    lang: str, profile: str, address_form: str, flags: Clock
) -> None:
    t = await Teacher(profile, address_form).setup()
    await due_and_offered(t, flags)
    out = await t.tap(followup.BTN_WORKED)
    text = alltext(out)
    assert stored_outcomes(t) == [("worked", None)]
    assert "!" not in text and "शाबाश" not in text and "great" not in text.lower()
    assert len(out) == 1
    if address_form == "m" and lang == "hi":
        assert not any(re.search(m, text) for m in FEMININE_MARKERS)
    if profile == "demo3":  # a later move exists on her path
        assert "LIT_" not in text and "NUM_" not in text


@pytest.mark.asyncio
async def test_worked_offers_the_next_move_button_when_done_and_one_exists(
    lang: str, flags: Clock
) -> None:
    from backend.app.sessions.state_machine import SessionStateEnum

    t = await Teacher("demo3", "f").setup()
    ctx = await t.ctx()
    ctx.current_state = SessionStateEnum.DONE
    await t.service._sync_context_to_db(ctx, t.teacher_id)
    await due_and_offered(t, flags)
    out = await t.tap(followup.BTN_WORKED)
    assert ids(out) == ["btn_next_move"]


@pytest.mark.asyncio
async def test_double_tap_stores_one_outcome_and_says_so(lang: str, flags: Clock) -> None:
    t = await Teacher("demo3", "f").setup()
    await due_and_offered(t, flags)
    await t.tap(followup.BTN_WORKED)
    again = await t.tap(followup.BTN_WORKED)
    assert stored_outcomes(t) == [("worked", None)]
    assert get_message("fu_already") in alltext(again)
    other = await t.tap(followup.BTN_STUCK)  # a different answer after the first is not stored
    assert stored_outcomes(t) == [("worked", None)]
    assert get_message("fu_already") in alltext(other)


# ── still stuck ──────────────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_stuck_gives_the_other_cited_chunk_and_the_practice_button(
    lang: str, flags: Clock
) -> None:
    t = await Teacher("demo3", "f").setup()
    await due_and_offered(t, flags)
    out = await t.tap(followup.BTN_STUCK)
    assert stored_outcomes(t) == [("stuck", None)]
    tip, offer = out
    assert [c.chunk_id for c in tip.citations] == [MAPPED.chunk_ids[1]]  # a DIFFERENT source
    assert MAPPED.chunk_ids[0] not in {c.chunk_id for c in tip.citations}
    assert followup.BTN_PRACTICE in ids([offer])
    assert checkin_flow.BTN_START not in ids(out)


@pytest.mark.asyncio
async def test_stuck_practice_button_opens_the_practice_and_clears_the_follow_up(
    flags: Clock,
) -> None:
    t = await Teacher("demo3", "f").setup()
    await due_and_offered(t, flags)
    await t.tap(followup.BTN_STUCK)
    out = await t.tap(followup.BTN_PRACTICE)
    ctx = await t.ctx()
    assert ctx.current_move_id == MAPPED.move_id
    assert out and ctx.followup_id == ""
    again = await t.tap(followup.BTN_PRACTICE)  # an old button: nothing restarts
    assert get_message("fu_already") in alltext(again)


@pytest.mark.asyncio
async def test_stuck_without_a_move_has_no_practice_button_and_says_so(
    lang: str, flags: Clock
) -> None:
    t = await Teacher("demo3", "f").setup()
    await due_and_offered(t, flags, "NUM_COUNTING")
    out = await t.tap(followup.BTN_STUCK)
    assert followup.BTN_PRACTICE not in ids(out)
    assert followup.BTN_HANDBOOK in ids(out)
    assert get_message("chk_practice_none") in alltext(out)


def test_stuck_with_one_stored_chunk_repeats_the_tip_with_an_honest_line() -> None:
    one = MAPPED.model_copy(update={"chunk_ids": MAPPED.chunk_ids[:1]})
    lib = StruggleLibrary(struggles=[one], other=LIB.other)
    ctx = SessionContext(teacher_id="t", week_start="2026-10-26", current_move_id="x")
    for code in ("hi", "en"):
        token = set_ui_lang(code)
        try:
            msgs = followup.stuck_messages(lib.struggles[0], ctx, in_scene=False)
        finally:
            reset_ui_lang(token)
        assert [c.chunk_id for c in msgs[0].citations] == MAPPED.chunk_ids[:1]
        assert get_message("fu_stuck_same", lang=code).split("{")[0] in msgs[0].text_hi


def test_stuck_with_no_stored_chunk_says_the_material_is_not_available() -> None:
    gone = MAPPED.model_copy(update={"chunk_ids": ["no:such:chunk"]})
    ctx = SessionContext(teacher_id="t", week_start="2026-10-26", current_move_id="x")
    msgs = followup.stuck_messages(gone, ctx, in_scene=False)
    assert not msgs[0].citations
    assert msgs[0].text_hi == get_message("chk_tip_missing", label=struggle_label(gone))


# ── could not try ────────────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_cant_asks_why_with_four_closed_options(lang: str, flags: Clock) -> None:
    t = await Teacher("demo3", "f").setup()
    await due_and_offered(t, flags)
    out = await t.tap(followup.BTN_CANT)
    assert ids(out) == [
        f"{followup.WHY_PREFIX}{r}" for r in ("time", "multigrade", "absent", "other")
    ]
    assert stored_outcomes(t) == [("cant", None)]


@pytest.mark.asyncio
@pytest.mark.parametrize("reason", followup.REASONS)
async def test_each_reason_is_stored_once_and_the_reply_is_practical_never_shaming(
    lang: str, reason: str, flags: Clock
) -> None:
    t = await Teacher("demo3", "f").setup()
    await due_and_offered(t, flags)
    await t.tap(followup.BTN_CANT)
    out = await t.tap(f"{followup.WHY_PREFIX}{reason}")
    text = alltext(out).lower()
    assert stored_outcomes(t) == [("cant", reason)]
    assert not any(w in text for w in ("should have", "चाहिए था", "lazy", "आलस", "!"))
    if reason == "multigrade":
        assert "btn_lvl_start" in ids(out)  # the level sorter
    else:
        assert "btn_lvl_start" not in ids(out)
        assert followup.BTN_HANDBOOK in ids(out)
    again = await t.tap(f"{followup.WHY_PREFIX}other")  # a second tap changes nothing
    assert stored_outcomes(t) == [("cant", reason)]
    assert get_message("fu_already") in alltext(again)


@pytest.mark.asyncio
async def test_multigrade_without_the_level_sorter_points_to_the_handbook_only(
    monkeypatch: pytest.MonkeyPatch, flags: Clock
) -> None:
    monkeypatch.setattr(settings, "LEVEL_SORTER_ENABLED", False)
    t = await Teacher("demo3", "f").setup()
    await due_and_offered(t, flags)
    await t.tap(followup.BTN_CANT)
    out = await t.tap(f"{followup.WHY_PREFIX}multigrade")
    assert ids(out) == [followup.BTN_HANDBOOK]


@pytest.mark.asyncio
async def test_why_without_cant_first_stores_nothing(flags: Clock) -> None:
    t = await Teacher("demo3", "f").setup()
    await due_and_offered(t, flags)
    out = await t.tap(f"{followup.WHY_PREFIX}time")
    assert stored_outcomes(t) == []
    assert get_message("fu_already") in alltext(out)


@pytest.mark.asyncio
async def test_handbook_button_opens_the_ask_prompt(flags: Clock) -> None:
    t = await Teacher("demo3", "f").setup()
    await due_and_offered(t, flags)
    await t.tap(followup.BTN_STUCK)
    out = await t.tap(followup.BTN_HANDBOOK)
    assert get_message("ask_prompt", "f") in alltext(out)


# ── channel caps ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_whatsapp_three_outcomes_are_reply_buttons_four_reasons_are_a_list(
    lang: str, flags: Clock
) -> None:
    t = await Teacher("demo3", "f").setup()
    await due_and_offered(t, flags)
    ask = followup.ask_message(MAPPED)
    plan = plan_buttons(ask.buttons or [], has_audio=False)
    assert len(plan.reply_buttons) == 3 and plan.list_rows == []
    why = followup.why_message()
    plan = plan_buttons(why.buttons or [], has_audio=False)
    assert plan.reply_buttons == [] and len(plan.list_rows) == 4
    assert all(len(title) <= settings.WHATSAPP_BUTTON_TITLE_MAX for _, title, _ in plan.list_rows)


def test_every_button_title_fits_twenty_characters_in_both_languages() -> None:
    keys = [*followup.OUTCOME_BUTTONS, *followup.WHY_BUTTONS, followup.BTN_PRACTICE]
    keys.append(followup.BTN_HANDBOOK)
    for code in ("hi", "en"):
        for key in keys:
            assert 0 < len(get_message(key, lang=code)) <= settings.WHATSAPP_BUTTON_TITLE_MAX, key


def test_new_text_has_no_em_or_en_dashes() -> None:
    for code in ("hi", "en"):
        for key in ("fu_ask", "fu_why_ask", "fu_worked_ack", "fu_stuck_other", "fu_stuck_same"):
            assert not any(d in get_message(key, lang=code) for d in DASHES), key
        for key in ("fu_cant_multigrade", "fu_cant_time", "fu_cant_absent", "fu_cant_other"):
            assert not any(d in get_message(key, lang=code) for d in DASHES), key
        assert not any(d in get_message("fu_tomorrow_focus", lang=code) for d in DASHES)


# ── tomorrow's focus (a pure function; nothing is sent) ──────────────────────────────────────
def test_tomorrow_focus_needs_the_opt_in_and_a_struggle() -> None:
    assert followup.tomorrow_focus("NUM_SUB_REGROUP", opted_in=False) is None
    assert followup.tomorrow_focus(None, opted_in=True) is None
    assert followup.tomorrow_focus("NOT_A_STRUGGLE", opted_in=True) is None


def test_tomorrow_focus_is_one_cited_step(lang: str) -> None:
    focus = followup.tomorrow_focus("NUM_SUB_REGROUP", opted_in=True)
    assert focus is not None and focus.struggle_id == "NUM_SUB_REGROUP"
    assert {c.chunk_id for c in focus.citations} == set(MAPPED.chunk_ids)
    tip = MAPPED.tip_en if lang == "en" else MAPPED.tip_hi
    assert tip in focus.text
    assert not any(d in focus.text for d in DASHES)


def test_tomorrow_focus_is_withheld_when_no_stored_chunk_backs_it() -> None:
    gone = MAPPED.model_copy(update={"chunk_ids": ["no:such:chunk"]})
    lib = StruggleLibrary(struggles=[gone], other=LIB.other)
    assert followup.tomorrow_focus(gone.id, opted_in=True, lib=lib) is None


def test_the_opt_in_defaults_to_off() -> None:
    from backend.app.db.models import Teacher as TeacherRow

    column = TeacherRow.__table__.c.tomorrow_focus_opt_in
    assert column.server_default is not None and column.nullable is False
