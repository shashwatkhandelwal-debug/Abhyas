"""fix3 K1: a child never nearly repeats his last line, and reacts when the teacher told him the steps.

The transcript is the live one: Ravi ("how did you get 45?"), then the teacher dictates the whole
procedure; Ravi's second line used to be the first with one word changed.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from backend.app.content_models import PersonaCard
from backend.app.llm.client import LLMUnavailable
from backend.app.llm.hindi_numbers import extract_numbers
from backend.app.llm.roles.child_voice import (
    is_near_repeat,
    reaction_for,
    teacher_is_telling,
    voice_child_line,
)
from backend.app.rule_engine.domain import ChildResponse, ChildState, Problem, ResponseKind, Step

PERSONA = PersonaCard(
    id="ravi",
    name_hi="रवि",
    age=7,
    temperament="confident",
    voice_id="child_ravi",
    speech_style_hi="जल्दी और पूरे भरोसे से बोलता है",
    off_topic_lines_hi=["दीदी, आज खेल का पीरियड होगा?"],
)
FIRST = "सर, तो 7 में से 2 घटाया, 5 आया। 5 में से 1 घटाया, 4 आया। तो 45!"
LIVE_SECOND = "सर, तो 7 में से 2 घटाया, 5 आया। 5 में से 1 घटाया, 4 आया। उत्तर 45!"
ASKED = "Ravi, how did you get 45?"
TOLD = "ऊपर 52 नीचे 17 लिखो, 12 में से 7 घटाओ, 4 में से 1 घटाओ, अब बताओ क्या आंसर है"


def _resp(kind: ResponseKind = ResponseKind.RELAPSE) -> ChildResponse:
    return ChildResponse(
        persona_id="ravi",
        kind=kind,
        answer=45,
        prior_state=ChildState.MISCONCEPTION,
        new_state=ChildState.MISCONCEPTION,
        affect="confident",
        item=Problem(type="sub", a=52, b=17),
        steps=[
            Step(code="SUB_SMALLER_FROM_LARGER", text_hi="7 में से 2 घटाया, 5 आया", nums=[7, 2, 5]),
            Step(code="SUB_TENS", text_hi="5 में से 1 घटाया, 4 आया", nums=[5, 1, 4]),
        ],
        allowed_numbers={7, 2, 5, 1, 4, 45},
        forbidden={"35"},
    )


def test_the_live_second_line_is_a_near_repeat() -> None:
    assert is_near_repeat(LIVE_SECOND, FIRST)
    assert not is_near_repeat("मुझे ठीक से समझ नहीं आया। पहला कदम फिर से बताइए?", FIRST)
    assert not is_near_repeat(FIRST, None)


def test_address_word_and_fillers_do_not_hide_a_repeat() -> None:
    assert is_near_repeat("दीदी, तो 12 में से 7 घटाया, 5 आया।", "सर, 12 में से 7 घटाया, 5 आया")


def test_telling_is_detected_from_text_or_acts() -> None:
    assert teacher_is_telling(TOLD)
    assert not teacher_is_telling(ASKED)
    assert not teacher_is_telling("रवि, बंडल लेकर 43 बनाओ और 27 हटाओ।")
    assert teacher_is_telling("कुछ भी", ["model_step_aloud"])
    assert reaction_for(_resp(), TOLD, [], FIRST) == "telling"
    assert reaction_for(_resp(), ASKED, ["ask_to_explain"], None) is None
    assert reaction_for(_resp(), "आज बारिश है न?", ["off_task"], FIRST) == "off_task"
    assert reaction_for(_resp(ResponseKind.SCAFFOLDED_CORRECT), TOLD, [], FIRST) is None


def _check_reacts(line: str) -> None:
    assert not is_near_repeat(line, FIRST), line
    assert not is_near_repeat(line, LIVE_SECOND), line
    assert line.startswith("सर"), line  # a male teacher: the right address word, never दीदी
    assert "दीदी" not in line
    assert not extract_numbers(line), line  # he reacts, he does not restate or invent an answer


@pytest.mark.asyncio
async def test_k1_template_path_reacts_to_the_telling() -> None:
    with patch(
        "backend.app.llm.roles.child_voice.call_tool",
        new=AsyncMock(side_effect=LLMUnavailable("x")),
    ):
        line = await voice_child_line(
            _resp(),
            PERSONA,
            turn_idx=2,
            address_form="m",
            previous_line=FIRST,
            teacher_said=TOLD,
            teacher_acts=[],
        )
    _check_reacts(line)


@pytest.mark.asyncio
async def test_k1_mock_model_path_reacts_to_the_telling() -> None:
    """A model that keeps returning the old line (as the mock does) still ends in a reaction."""
    with patch(
        "backend.app.llm.roles.child_voice.call_tool",
        new=AsyncMock(return_value={"line_hi": LIVE_SECOND}),
    ):
        line = await voice_child_line(
            _resp(),
            PERSONA,
            turn_idx=2,
            address_form="m",
            previous_line=FIRST,
            teacher_said=TOLD,
            teacher_acts=[],
        )
    _check_reacts(line)


@pytest.mark.asyncio
async def test_k1_model_may_react_in_its_own_words() -> None:
    own = "सर, मुझे समझ नहीं आया, पहला कदम फिर से बताइए?"
    with patch(
        "backend.app.llm.roles.child_voice.call_tool", new=AsyncMock(return_value={"line_hi": own})
    ):
        line = await voice_child_line(
            _resp(), PERSONA, address_form="m", previous_line=FIRST, teacher_said=TOLD
        )
    assert line == own


@pytest.mark.asyncio
@pytest.mark.parametrize("model_fails", [True, False])
async def test_k1_a_plain_repeat_without_telling_gets_a_different_line(model_fails: bool) -> None:
    """Teacher asks again (not telling): same state, but the line must not be the old one."""
    patched = (
        AsyncMock(side_effect=LLMUnavailable("x"))
        if model_fails
        else AsyncMock(return_value={"line_hi": LIVE_SECOND})
    )
    with patch("backend.app.llm.roles.child_voice.call_tool", new=patched):
        line = await voice_child_line(
            _resp(),
            PERSONA,
            turn_idx=3,
            address_form="m",
            previous_line=FIRST,
            teacher_said="रवि, एक बार और बताओ, कैसे किया?",
            teacher_acts=["ask_to_explain"],
        )
    assert not is_near_repeat(line, FIRST), line
    assert 45 in extract_numbers(line)
    assert "दीदी" not in line


@pytest.mark.asyncio
async def test_k1_off_task_remark_gets_a_reaction() -> None:
    with patch(
        "backend.app.llm.roles.child_voice.call_tool",
        new=AsyncMock(side_effect=LLMUnavailable("x")),
    ):
        line = await voice_child_line(
            _resp(),
            PERSONA,
            turn_idx=1,
            address_form="f",
            previous_line=FIRST,
            teacher_said="आज बाहर बारिश हो रही है न?",
            teacher_acts=["off_task"],
        )
    assert line.startswith("दीदी") and not extract_numbers(line)
    assert not is_near_repeat(line, FIRST)
