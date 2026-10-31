"""L1: "My progress" (flag MY_PROGRESS_ENABLED): trend logic on fixed histories, the too-few case,
the entry buttons, Hindi and English, she and he, WhatsApp caps, flag off. No model is involved."""

from __future__ import annotations

import re
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from test_class_checkin import Teacher, alltext, ids

from backend.app.channels.whatsapp.buttons import plan_buttons
from backend.app.class_profile import my_progress
from backend.app.config import settings
from backend.app.core.messages import FEMININE_MARKERS, get_message, reset_ui_lang, set_ui_lang
from backend.app.core.types import Button
from backend.app.sessions.rehearsal_view import Rehearsal, TurnView
from backend.app.sessions.service import SessionService
from backend.app.sessions.state_machine import SessionStateEnum

MOVE = "NUM_SUB_REGROUP_BUNDLES"
OTHER = "NUM_ADD_CARRY_BUNDLES"
BASE = datetime(2026, 10, 20, 10, 0, tzinfo=UTC)
DASHES = ("—", "–")
TOO_FEW = {"hi": "अभी तुलना के लिए कम अभ्यास हैं", "en": "too few practices to compare"}


def turn(acts: list[str], child: str = "all", text: str = "बच्चों, घटाओ") -> TurnView:
    return TurnView(text, tuple(acts), child)


def reh(day: int, turns: list[TurnView], *, move: str = MOVE, one: bool = False) -> Rehearsal:
    return Rehearsal(move, BASE + timedelta(days=day), one, tuple(turns))


TOLD = turn(["tell_answer"])
ASKED = turn(["ask_to_explain"])
CONCRETE = turn(["concrete_representation"])
NAMED_ASK = turn(["ask_to_explain"], child="priya")
# first: told, never asked, no objects, whole class; last: asked, not told, objects, named a child
FIRST = reh(0, [TOLD, turn(["repeat_question"])])
MIDDLE = reh(3, [ASKED, TOLD])
LAST = reh(6, [NAMED_ASK, CONCRETE])
BUTTON = [Button(id=my_progress.BTN_PRACTICE, title_hi="x")]


@pytest.fixture(autouse=True)
def flags(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "MY_PROGRESS_ENABLED", True)
    monkeypatch.setattr(settings, "CLASS_CHECKIN_ENABLED", True)
    monkeypatch.setattr(settings, "DEMO_MODE", False)


@pytest.fixture(params=["hi", "en"])
def lang(request: pytest.FixtureRequest) -> Iterator[str]:
    token = set_ui_lang(request.param)
    yield request.param
    reset_ui_lang(token)


def text_of(history: list[Rehearsal], address_form: str = "f") -> str:
    return my_progress.progress_message(history, address_form, BUTTON).text_hi or ""


# ── facts and the trend, on fixed histories ──────────────────────────────────────────────────
def test_facts_from_the_tagged_acts() -> None:
    assert my_progress.facts_of(FIRST) == {
        "asked": False,
        "told": True,
        "concrete": False,
        "named": False,
    }
    assert my_progress.facts_of(LAST) == {
        "asked": True,
        "told": False,
        "concrete": True,
        "named": True,
    }


def test_one_on_one_has_no_named_fact_and_no_turn_has_no_facts() -> None:
    assert my_progress.facts_of(reh(0, [ASKED], one=True))["named"] is None
    assert set(my_progress.facts_of(reh(0, [])).values()) == {None}
    stop = turn(["stop"], text="रुको")
    assert set(my_progress.facts_of(reh(0, [stop])).values()) == {None}


def test_the_pair_is_the_earliest_and_latest_of_the_same_move() -> None:
    other = reh(8, [ASKED], move=OTHER)
    pair = my_progress.pick_pair([LAST, other, FIRST, MIDDLE])
    assert pair is not None and pair == (FIRST, LAST)
    assert my_progress.pick_pair([FIRST, other]) is None


def test_the_trend_compares_first_and_latest_per_fact(lang: str) -> None:
    text = text_of([FIRST, MIDDLE, LAST])
    yes, no = get_message("mp_yes"), get_message("mp_no")
    lines = [ln for ln in text.splitlines() if get_message("mp_l_told") in ln]
    assert lines == [
        get_message("mp_trend_line", label=get_message("mp_l_told"), before=yes, after=no)
    ]
    assert get_message("mp_trend_head", move="").split(":")[0] in text
    for label in ("mp_l_asked", "mp_l_concrete", "mp_l_named"):
        assert get_message(label) in text


def test_one_strength_and_one_next_step_are_deterministic(lang: str) -> None:
    first = text_of([FIRST, MIDDLE, LAST])
    assert first == text_of([FIRST, MIDDLE, LAST])
    assert sum(ln.startswith(get_message("mp_s_asked")[:6]) for ln in first.splitlines()) >= 1
    # improvement order: asked comes first, and everything is good in LAST so the step is "keep"
    assert get_message("mp_s_asked") in first
    assert get_message("mp_n_keep") in first
    assert first.count(get_message("mp_n_keep")[:10]) == 1


def test_next_step_names_the_first_thing_still_missing(lang: str) -> None:
    told_again = reh(6, [TOLD, ASKED])
    text = text_of([FIRST, told_again])
    assert get_message("mp_n_told") in text
    no_objects = reh(6, [ASKED])
    assert get_message("mp_n_concrete") in text_of([reh(0, [ASKED]), no_objects])


def test_only_the_last_five_are_listed() -> None:
    history = [reh(d, [ASKED]) for d in range(8)]
    text = text_of(history)
    assert text.count("\n") >= 5
    rows = [ln for ln in text.splitlines() if re.match(r"^\d\. ", ln)]
    assert len(rows) == settings.MY_PROGRESS_SHOWN == 5
    assert (
        rows[-1].startswith("5. ") and "27 " in rows[-1] and "/" not in rows[-1]
    )  # the newest, a day and a month name


def test_different_moves_say_a_comparison_needs_the_same_move(lang: str) -> None:
    text = text_of([reh(0, [TOLD]), reh(2, [ASKED], move=OTHER)])
    assert get_message("mp_no_pair") in text
    assert get_message("mp_trend_head", move="").split(":")[0] not in text
    assert get_message("mp_n_asked") not in text  # she asked in the latest one


@pytest.mark.parametrize("count", [0, 1])
def test_fewer_than_two_rehearsals_says_so_and_keeps_a_button(lang: str, count: int) -> None:
    msg = my_progress.progress_message([FIRST][:count], "f", BUTTON)
    assert TOO_FEW[lang] in (msg.text_hi or "")
    assert ids([msg]) == [my_progress.BTN_PRACTICE]  # never a dead end
    assert "mp_" not in (msg.text_hi or "") and "{" not in (msg.text_hi or "")


def test_her_own_words_are_never_quoted() -> None:
    secret = TurnView("गुप्त वाक्य पहचान", ("ask_to_explain",), "all")
    assert "गुप्त" not in text_of([reh(0, [TOLD]), reh(2, [secret])])


@pytest.mark.parametrize("address_form", ["f", "m"])
def test_he_gets_no_feminine_forms(address_form: str) -> None:
    token = set_ui_lang("hi")
    try:
        text = text_of([FIRST, MIDDLE, LAST], address_form)
    finally:
        reset_ui_lang(token)
    if address_form == "m":
        assert not any(re.search(m, text) for m in FEMININE_MARKERS)


# ── catalog ──────────────────────────────────────────────────────────────────────────────────
KEYS = [
    "btn_mp_practice", "mp_head", "mp_row", "mp_trend_head", "mp_trend_line", "mp_yes", "mp_no",
    "mp_l_asked", "mp_l_told", "mp_l_concrete", "mp_l_named", "mp_no_pair", "mp_too_few",
    "mp_s_asked", "mp_s_notold", "mp_s_concrete", "mp_s_named", "mp_s_none", "mp_n_told",
    "mp_n_asked", "mp_n_concrete", "mp_n_named", "mp_n_keep",
]  # fmt: skip


def test_both_languages_have_every_key_with_no_dashes() -> None:
    for key in KEYS:
        hi, en = get_message(key, lang="hi"), get_message(key, lang="en")
        assert hi and en and hi != en or key in ("mp_row",), key
        assert not any(d in hi + en for d in DASHES), key


def test_the_practice_button_fits_the_whatsapp_title_cap() -> None:
    for code in ("hi", "en"):
        assert (
            0 < len(get_message("btn_mp_practice", lang=code)) <= settings.WHATSAPP_BUTTON_TITLE_MAX
        )


# ── through the real service ─────────────────────────────────────────────────────────────────
async def teacher(state: SessionStateEnum, history: list[Rehearsal], form: str = "f") -> Teacher:
    t = await Teacher("demo2", form).setup()
    ctx = await t.ctx()
    ctx.current_state = state
    await t.service._sync_context_to_db(ctx, t.teacher_id)
    t.repo._rehearsal_history = {t.teacher_id: history}  # type: ignore[attr-defined]
    return t


@pytest.mark.asyncio
async def test_done_screen_progress_shows_the_trend_and_a_next_step(lang: str) -> None:
    t = await teacher(SessionStateEnum.DONE, [FIRST, MIDDLE, LAST])
    out = await t.tap("btn_progress")
    assert len(out) == 1 and out[0].buttons
    assert get_message("mp_trend_head", move="").split(":")[0] in alltext(out)
    assert ids(out)[0] == "btn_next_move"
    assert 1 <= len(out[0].buttons) <= 3
    plan = plan_buttons(out[0].buttons, has_audio=False)
    assert len(plan.reply_buttons) + len(plan.list_rows) == len(out[0].buttons)
    assert all(len(b.title_hi) <= settings.WHATSAPP_BUTTON_TITLE_MAX for b in out[0].buttons)


@pytest.mark.asyncio
async def test_typed_words_work_on_a_button_screen(lang: str) -> None:
    t = await teacher(SessionStateEnum.DONE, [FIRST, LAST])
    out = await t.say("मेरी प्रगति")
    assert get_message("mp_head", n=2).split(",")[0] in alltext(out)


@pytest.mark.asyncio
async def test_too_few_in_the_service_offers_practice(lang: str) -> None:
    t = await teacher(SessionStateEnum.DONE, [FIRST])
    out = await t.tap("btn_progress")
    assert TOO_FEW[lang] in alltext(out)
    assert my_progress.BTN_PRACTICE in ids(out)
    opened = await t.tap(my_progress.BTN_PRACTICE)  # the practice button really opens a practice
    assert opened and (await t.ctx()).current_state == SessionStateEnum.REHEARSE_INTRO


@pytest.mark.asyncio
async def test_feedback_screen_keeps_its_own_buttons() -> None:
    t = await teacher(SessionStateEnum.FEEDBACK, [FIRST, LAST])
    out = await t.tap("btn_progress")
    assert ids(out) == ["btn_retry", "btn_continue"]


@pytest.mark.asyncio
async def test_inside_a_scene_only_the_exact_typed_command_opens_it_and_the_scene_stays() -> None:
    """fix3 B07: the demo2 banner says to open "मेरी प्रगति"; a line said to a child never counts."""
    t = await teacher(SessionStateEnum.REHEARSE, [FIRST, LAST])
    seen: list[Any] = []
    orig = SessionService._my_progress_messages

    async def spy(self: SessionService, *a: Any, **k: Any) -> Any:
        seen.append(1)
        return await orig(self, *a, **k)

    SessionService._my_progress_messages = spy  # type: ignore[method-assign]
    try:
        await t.tap("btn_progress")  # the button is never offered in a scene: no progress
        assert seen == []
        out = await t.say("मेरी प्रगति")  # the whole line is the command
        assert seen == [1]
        assert get_message("mp_head", n=2).split(",")[0] in alltext(out)
        assert len(out) == 2 and not out[0].buttons  # the progress, then back to the scene
        assert (await t.ctx()).current_state == SessionStateEnum.REHEARSE
        seen.clear()
        await t.say("रवि, मेरी प्रगति कैसी है, बताओ")  # said to a child: a normal teacher turn
        assert seen == []
    finally:
        SessionService._my_progress_messages = orig  # type: ignore[method-assign]


def test_the_quick_reply_follows_the_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    assert [b.id for b in SessionService._progress_entry_buttons("f")] == ["btn_progress"]
    monkeypatch.setattr(settings, "MY_PROGRESS_ENABLED", False)
    assert SessionService._progress_entry_buttons("f") == []


@pytest.mark.asyncio
async def test_flag_off_keeps_the_old_one_line_summary(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "MY_PROGRESS_ENABLED", False)
    t = await teacher(SessionStateEnum.DONE, [FIRST, MIDDLE, LAST])
    out = await t.tap("btn_progress")
    assert get_message("progress_summary", n_done=1, lines="").split(":")[0] in alltext(out)
    assert get_message("mp_trend_head", move="").split(":")[0] not in alltext(out)
    assert settings.model_fields["MY_PROGRESS_ENABLED"].default is False


@pytest.mark.asyncio
async def test_demo_mode_turns_it_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "MY_PROGRESS_ENABLED", False)
    monkeypatch.setattr(settings, "DEMO_MODE", True)
    t = await teacher(SessionStateEnum.DONE, [FIRST, LAST])
    assert get_message("mp_head", n=2).split(",")[0] in alltext(await t.tap("btn_progress"))


@pytest.mark.parametrize(("lang", "expected"), [("hi", "21 अक्टूबर"), ("en", "21 Oct")])
def test_b08_a_date_reads_as_a_date_not_a_score(lang: str, expected: str) -> None:
    """fix3 B08: "(21/10)" read like a score of 21 out of 10."""
    from datetime import UTC, datetime

    token = set_ui_lang(lang)
    try:
        shown = my_progress._date(datetime(2026, 10, 21, 6, 0, tzinfo=UTC))
    finally:
        reset_ui_lang(token)
    assert shown == expected and "/" not in shown
