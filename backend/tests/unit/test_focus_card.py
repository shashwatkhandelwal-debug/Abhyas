"""Today's focus ("आज का सुझाव"): opt-in, once a day, ordering, scene safety, citations, caps."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from test_class_checkin import Teacher, ids, open_module, struggle_button  # noqa: F401
from test_state_machine import FakeSessionRepository

from backend.app.channels.whatsapp.buttons import plan_buttons
from backend.app.class_profile import checkin_flow, focus, followup
from backend.app.config import settings
from backend.app.core.messages import get_message, reset_ui_lang, set_ui_lang
from backend.app.core.types import OutboundMessage
from backend.app.sessions.state_machine import SessionStateEnum

IST = ZoneInfo("Asia/Kolkata")
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
    monkeypatch.setattr(settings, "DEMO_MODE", False)
    monkeypatch.setattr(settings, "CLASS_CHECKIN_ENABLED", True)
    monkeypatch.setattr(settings, "FOLLOWUP_ENABLED", True)
    monkeypatch.setattr(settings, "FOCUS_CARD_ENABLED", True)
    clock = Clock(at(FRIDAY))
    monkeypatch.setattr(followup, "utcnow", clock)

    async def last_button_time(
        self: FakeSessionRepository, teacher_id: Any, button_ids: tuple[str, ...]
    ) -> datetime | None:
        sent = [t for t, ids_ in getattr(self, "_sent", []) if set(ids_) & set(button_ids)]
        return max(sent, default=None)

    monkeypatch.setattr(FakeSessionRepository, "last_outbound_button_time", last_button_time)
    return clock


@pytest.fixture(params=["hi", "en"])
def lang(request: pytest.FixtureRequest) -> Iterator[str]:
    token = set_ui_lang(request.param)
    yield request.param
    reset_ui_lang(token)


async def deliver(t: Teacher, clock: Clock, out: list[OutboundMessage]) -> None:
    """The web route persists what offer_focus returned; the fake repo records the buttons sent."""
    sent: list[Any] = getattr(t.repo, "_sent", [])
    for m in out:
        sent.append((clock.moment, [b.id for b in m.buttons]))
    t.repo._sent = sent  # type: ignore[attr-defined]


async def check_in(t: Teacher, struggle_id: str = "NUM_SUB_REGROUP") -> None:
    module = next(m.id for m in checkin_flow.modules() if struggle_id in m.struggle_ids)
    await open_module(t, module)
    await t.tap("btn_chk_most")
    await t.tap(struggle_button(struggle_id))


async def opted_in(t: Teacher) -> None:
    teacher = await t.repo.get_or_create_teacher(t.teacher_id)
    teacher.tomorrow_focus_opt_in = True
    await t.repo.save_teacher(teacher)


async def is_opted_in(t: Teacher) -> bool:
    return bool((await t.repo.get_or_create_teacher(t.teacher_id)).tomorrow_focus_opt_in)


@pytest.mark.asyncio
async def test_no_offer_before_a_check_in_or_finished_practice() -> None:
    t = await Teacher("demo3", "f").setup()
    assert await t.service.offer_focus(t.teacher_id) == []


@pytest.mark.asyncio
async def test_offer_after_a_check_in_once_a_week(flags: Clock, lang: str) -> None:
    t = await Teacher("demo3", "f").setup()
    await check_in(t)
    out = await t.service.offer_focus(t.teacher_id)
    assert [m.text_hi for m in out] == [get_message("focus_offer")]
    assert ids(out) == [focus.BTN_YES, focus.BTN_NO]
    await deliver(t, flags, out)
    flags.moment = at(FRIDAY + timedelta(days=3))
    assert await t.service.offer_focus(t.teacher_id) == []  # not again within the week
    flags.moment = at(FRIDAY + timedelta(days=8))
    assert ids(await t.service.offer_focus(t.teacher_id)) == [focus.BTN_YES, focus.BTN_NO]


@pytest.mark.asyncio
async def test_yes_opts_in_not_now_does_not_and_turn_off_opts_out(flags: Clock, lang: str) -> None:
    t = await Teacher("demo3", "f").setup()
    await check_in(t)
    assert not await is_opted_in(t)
    await deliver(t, flags, await t.service.offer_focus(t.teacher_id))  # the question was shown
    out = await t.tap(focus.BTN_NO)
    assert out[0].text_hi == get_message("focus_snooze_ack") and not await is_opted_in(t)
    out = await t.tap(focus.BTN_YES)
    assert out[0].text_hi == get_message("focus_on_ack") and await is_opted_in(t)
    out = await t.tap(focus.BTN_OFF)
    assert out[0].text_hi == get_message("focus_off_ack") and not await is_opted_in(t)
    flags.moment = at(FRIDAY + timedelta(days=1))
    assert await t.service.offer_focus(t.teacher_id) == []  # opted out: no card


@pytest.mark.asyncio
async def test_card_has_one_cited_step_and_a_next_step_button(flags: Clock, lang: str) -> None:
    t = await Teacher("demo3", "f").setup()
    await check_in(t, "NUM_SUB_REGROUP")
    await opted_in(t)
    out = await t.service.offer_focus(t.teacher_id)
    assert len(out) == 1
    card = out[0]
    assert (card.text_hi or "").startswith(get_message("focus_card_head"))
    assert card.citations  # a focus card is never sent without a stored citation
    assert ids(out) == [focus.BTN_PRACTICE, focus.BTN_ASK, focus.BTN_OFF]
    assert not any(d in (card.text_hi or "") for d in DASHES)


@pytest.mark.asyncio
async def test_card_for_a_struggle_with_no_practice_has_ask_and_off_only(flags: Clock) -> None:
    t = await Teacher("demo3", "f").setup()
    await check_in(t, "NUM_COUNTING")
    await opted_in(t)
    assert ids(await t.service.offer_focus(t.teacher_id)) == [focus.BTN_ASK, focus.BTN_OFF]


@pytest.mark.asyncio
async def test_at_most_one_card_a_day(flags: Clock) -> None:
    t = await Teacher("demo3", "f").setup()
    await check_in(t)
    await opted_in(t)
    out = await t.service.offer_focus(t.teacher_id)
    assert out
    await deliver(t, flags, out)
    flags.moment = at(FRIDAY, 18)  # later the same Indian day
    assert await t.service.offer_focus(t.teacher_id) == []
    flags.moment = at(FRIDAY + timedelta(days=1), 8)
    assert await t.service.offer_focus(t.teacher_id)


@pytest.mark.asyncio
async def test_never_interrupts_a_scene_she_has_started(flags: Clock) -> None:
    t = await Teacher("demo3", "f").setup()
    await check_in(t)
    await opted_in(t)
    ctx = await t.ctx()
    ctx.current_state = SessionStateEnum.REHEARSE
    ctx.rehearsal_turns_count = 1
    await t.service._sync_context_to_db(ctx, t.teacher_id)
    assert await t.service.offer_focus(t.teacher_id) == []
    ctx.rehearsal_turns_count = 0  # she has not spoken yet: the card may come first
    await t.service._sync_context_to_db(ctx, t.teacher_id)
    assert await t.service.offer_focus(t.teacher_id)


@pytest.mark.asyncio
async def test_card_comes_after_the_due_follow_up_and_leaves_it_working(flags: Clock) -> None:
    t = await Teacher("demo3", "f").setup()
    await check_in(t)
    await opted_in(t)
    flags.moment = at(FRIDAY + timedelta(days=1))  # Saturday: the follow-up is due
    first = await t.service.offer_followup(t.teacher_id)
    assert ids(first) == [followup.BTN_WORKED, followup.BTN_STUCK, followup.BTN_CANT]
    second = await t.service.offer_focus(t.teacher_id)  # what the route does next
    assert ids(second) == [focus.BTN_PRACTICE, focus.BTN_ASK, focus.BTN_OFF]
    out = await t.tap(followup.BTN_WORKED)  # the follow-up still answers
    assert out and len(t.repo._followup_outcomes) == 1


@pytest.mark.asyncio
async def test_practice_button_opens_the_practice_and_ask_opens_the_handbook(flags: Clock) -> None:
    t = await Teacher("demo3", "f").setup()
    await check_in(t, "NUM_SUB_REGROUP")
    await opted_in(t)
    out = await t.tap(focus.BTN_PRACTICE)
    ctx = await t.ctx()
    assert ctx.current_move_id == "NUM_SUB_REGROUP_BUNDLES"
    assert ctx.current_state == SessionStateEnum.REHEARSE_INTRO and out
    t2 = await Teacher("demo3", "f").setup()
    await check_in(t2, "NUM_SUB_REGROUP")
    out = await t2.tap(focus.BTN_ASK)
    assert (await t2.ctx()).current_state == SessionStateEnum.ASK
    assert out[0].text_hi == get_message("ask_prompt", "f")


@pytest.mark.asyncio
async def test_flag_off_nothing_happens_and_buttons_store_nothing(
    flags: Clock, monkeypatch: pytest.MonkeyPatch
) -> None:
    t = await Teacher("demo3", "f").setup()
    await check_in(t)
    await opted_in(t)
    monkeypatch.setattr(settings, "FOCUS_CARD_ENABLED", False)
    assert await t.service.offer_focus(t.teacher_id) == []
    await t.tap(focus.BTN_OFF)
    assert await is_opted_in(t)  # the tap was not handled by the focus flow


def test_both_languages_have_every_text_and_titles_fit_whatsapp() -> None:
    keys = [
        "focus_offer",
        "focus_card_head",
        "focus_on_ack",
        "focus_snooze_ack",
        "focus_off_ack",
        *focus.ALL_BUTTONS,
    ]
    for code in ("hi", "en"):
        for key in keys:
            text = get_message(key, lang=code)
            assert text and not any(d in text for d in DASHES), key
    for code in ("hi", "en"):
        for key in focus.ALL_BUTTONS:
            title = get_message(key, lang=code)
            assert len(title) <= settings.WHATSAPP_BUTTON_TITLE_MAX, key
    assert get_message("focus_offer", lang="hi") == "क्या हर दिन चैट खोलने पर एक छोटा सुझाव दिखाएँ?"
    assert get_message("focus_card_head", lang="hi") == "आज का सुझाव"


@pytest.mark.asyncio
async def test_whatsapp_reply_button_caps(flags: Clock) -> None:
    t = await Teacher("demo3", "f").setup()
    await check_in(t)
    await opted_in(t)
    card = (await t.service.offer_focus(t.teacher_id))[0]
    plan = plan_buttons(card.buttons or [], has_audio=False)
    assert len(plan.reply_buttons) == 3 and plan.list_rows == []
    offer = plan_buttons(focus.offer_message().buttons or [], has_audio=False)
    assert len(offer.reply_buttons) == 2


def test_pure_decisions() -> None:
    now = at(FRIDAY)
    assert not focus.offer_due(opted_in=True, has_activity=True, last_offer_at=None, now=now)
    assert not focus.offer_due(opted_in=False, has_activity=False, last_offer_at=None, now=now)
    assert focus.offer_due(opted_in=False, has_activity=True, last_offer_at=None, now=now)
    assert not focus.card_due(opted_in=False, last_card_at=None, now=now)
    assert focus.card_due(opted_in=True, last_card_at=now - timedelta(days=1), now=now)
    assert not focus.card_due(opted_in=True, last_card_at=now - timedelta(hours=1), now=now)
    assert focus.last_struggle([["A"], [], ["B"]], ["C"]) == "B"
    assert focus.last_struggle([[]], ["C"]) == "C"
    assert focus.last_struggle([], []) is None
    assert focus.card_messages("NOT_A_STRUGGLE") == []
