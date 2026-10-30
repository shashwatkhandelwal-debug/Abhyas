"""F2: a question to the app never reaches the child (matcher in both directions, then the flow)."""

# ruff: noqa: F811  (the harness fixture is reused by name)
from __future__ import annotations

from collections.abc import Callable, Iterator

import pytest
from test_one_on_one_flow import Harness, harness  # noqa: F401

from backend.app.class_profile import checkin_flow, level_sorter
from backend.app.config import settings
from backend.app.core.help_question import is_help_question
from backend.app.core.messages import get_message, reset_ui_lang, set_ui_lang
from backend.app.sessions.state_machine import OnboardingStateEnum, SessionStateEnum

MODULE = "NUM_SUB_REGROUP_BUNDLES"

HELP_LINES = [
    "अब क्या करें",
    "अब क्या करें?",
    "अब क्या करूँ",
    "अब क्या करूं ?",
    "क्या करना है",
    "आगे क्या",
    "मदद",
    "समझ नहीं आया क्या करूँ",
    "ab kya karein",
    "Ab kya karien ?",
    "ab kya kare",
    "AB KYA KARE!",
    "kya karna hai",
    "aage kya",
    "help",
    "Help!",
    "what now",
    "What should I do?",
    "what next",
    "How does this work?",
    "  अब   क्या करें  ।",
]

TEACHING_LINES = [
    "रवि, अब क्या करोगे?",
    "अब 61 में से 28 घटाओ",
    "रवि, बताओ कैसे किया",
    "अब क्या करोगे",
    "अब क्या करो",
    "ravi ab kya karoge",
    "प्रिया, आगे क्या",
    "Aman, what now?",
    "तुमने यह कैसे किया?",
    "बंडल खोलकर गिनो।",
    "अब ये करो।",
    "इसे 43 में से 27 घटाओ",
    "यह शब्द पढ़ो",
    "",
    "अब आगे क्या करना है यह तुम बताओ और फिर समझाओ बच्चों को पूरी बात विस्तार से",
]


@pytest.mark.parametrize("line", HELP_LINES)
def test_help_phrases_are_caught(line: str) -> None:
    assert is_help_question(line)


@pytest.mark.parametrize("line", TEACHING_LINES)
def test_teaching_lines_are_not_caught(line: str) -> None:
    assert not is_help_question(line)


def test_none_is_not_a_question() -> None:
    assert not is_help_question(None)


@pytest.fixture(autouse=True)
def flags(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "CLASS_CHECKIN_ENABLED", True)
    monkeypatch.setattr(settings, "LEVEL_SORTER_ENABLED", True)
    monkeypatch.setattr(settings, "FOLLOWUP_ENABLED", False)
    monkeypatch.setattr(settings, "DEMO_MODE", False)


@pytest.fixture(params=["hi", "en"])
def lang(request: pytest.FixtureRequest) -> Iterator[str]:
    token = set_ui_lang(request.param)
    yield request.param
    reset_ui_lang(token)


@pytest.mark.asyncio
async def test_a_help_question_mid_scene_leaves_the_scene_untouched(
    harness: Callable[[], Harness], lang: str
) -> None:
    from backend.app.rule_engine.domain import TeachingAct

    h = harness()
    await h.setup(MODULE, "ravi", "उल्टा घटा दिया")
    h.script += [([TeachingAct.ASK_TO_EXPLAIN], None, None)]
    await h.say("तुमने कैसे किया?")
    scene = await h.scene()
    ctx = await h.ctx()
    turns, states = scene.scene_state.teacher_turns, [c.state for c in scene.scene_state.children]
    n_turns, ctx_turns = len(scene.turns), ctx.rehearsal_turns_count
    for line in ("Ab kya karien ?", "अब क्या करें", "what now"):
        out = await h.say(line)  # the script is empty: reaching the scene tagger would raise
        assert out[0].speaker == "coach"
        assert get_message("help_scene_stop") in (out[0].text_hi or "")
        assert "{" not in (out[0].text_hi or "")
    scene = await h.scene()
    assert scene.scene_state.teacher_turns == turns and len(scene.turns) == n_turns
    assert [c.state for c in scene.scene_state.children] == states
    assert (await h.ctx()).rehearsal_turns_count == ctx_turns


@pytest.mark.asyncio
async def test_a_teaching_line_still_reaches_the_scene(harness: Callable[[], Harness]) -> None:
    from backend.app.rule_engine.domain import TeachingAct

    h = harness()
    await h.setup(MODULE, "ravi", "उल्टा घटा दिया")
    h.script += [([TeachingAct.ASK_TO_EXPLAIN], "ravi", None)]
    out = await h.say("रवि, अब क्या करोगे?")
    assert (await h.scene()).scene_state.teacher_turns == 1
    assert out and out[0].speaker != "coach"


@pytest.mark.asyncio
async def test_help_at_the_name_step_gives_the_name_hint_and_stores_nothing(
    harness: Callable[[], Harness], lang: str
) -> None:
    h = harness()
    await h.start(MODULE)
    ctx = await h.ctx()
    ctx.onboarding_state = OnboardingStateEnum.PROFILE_NAME
    ctx.name = None
    await h.service._sync_context_to_db(ctx, h.teacher_id)
    out = await h.say("मदद" if lang == "hi" else "help")
    assert out[0].text_hi == get_message("hint_name", "f")
    ctx = await h.ctx()
    assert ctx.onboarding_state == OnboardingStateEnum.PROFILE_NAME and not ctx.name


@pytest.mark.asyncio
async def test_help_at_the_learn_step_gives_the_learn_hint_and_the_button(
    harness: Callable[[], Harness], lang: str
) -> None:
    h = harness()
    await h.start(MODULE)
    ctx = await h.ctx()
    ctx.current_state = SessionStateEnum.LEARN
    await h.service._sync_context_to_db(ctx, h.teacher_id)
    out = await h.say("ab kya kare")
    expected = get_message("hint_learn", "f", understood=get_message("btn_understood", "f"))
    assert out[0].text_hi == expected
    assert [b.id for b in out[0].buttons] == ["btn_understood"]
    assert (await h.ctx()).current_state == SessionStateEnum.LEARN


@pytest.mark.asyncio
async def test_help_in_the_check_in_and_the_level_sorter_returns_the_screen_hint(
    harness: Callable[[], Harness], lang: str
) -> None:
    h = harness()
    await h.start(MODULE)
    await h.say(button=checkin_flow.BTN_START)
    stage = (await h.ctx()).checkin_stage
    out = await h.say("what now")
    assert out[0].text_hi == get_message("hint_checkin", "f")
    assert (await h.ctx()).checkin_stage == stage
    checkin_flow.finish(await h.ctx())
    await h.say(button=level_sorter.BTN_START)
    level = (await h.ctx()).level_stage
    assert level
    out = await h.say("आगे क्या")
    assert out[0].text_hi == get_message("hint_checkin", "f")
    assert (await h.ctx()).level_stage == level


@pytest.mark.asyncio
async def test_help_at_the_done_screen_offers_the_next_buttons(
    harness: Callable[[], Harness], lang: str
) -> None:
    h = harness()
    await h.start(MODULE)
    ctx = await h.ctx()
    ctx.current_state = SessionStateEnum.DONE
    await h.service._sync_context_to_db(ctx, h.teacher_id)
    out = await h.say("help")
    assert [b.id for b in out[0].buttons] == ["btn_next_move", "btn_progress"]
    assert all(len(b.title_hi) <= 20 for b in out[0].buttons)
