"""F4: a child kept in the same state never says his previous line again, word for word."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from backend.app.content_models import PersonaCard
from backend.app.llm.guards import guard_child_line
from backend.app.llm.roles.child_voice import template_line, voice_child_line
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


def _resp(kind: ResponseKind) -> ChildResponse:
    return ChildResponse(
        persona_id="ravi",
        kind=kind,
        answer=45,
        prior_state=ChildState.MISCONCEPTION,
        new_state=ChildState.MISCONCEPTION,
        affect="confident",
        item=Problem(type="sub", a=52, b=17),
        steps=[Step(code="SUB_SMALLER_FROM_LARGER", text_hi="7 में से 2 गया 5", nums=[7, 2, 5])],
        allowed_numbers={7, 2, 5, 45},
        forbidden={"35"},
    )


@pytest.mark.parametrize(
    "kind",
    [ResponseKind.ANSWER, ResponseKind.EXPLAIN_BUG, ResponseKind.RELAPSE, ResponseKind.PARROT],
)
def test_consecutive_same_state_template_lines_differ(kind: ResponseKind) -> None:
    resp = _resp(kind)
    first = template_line(resp, PERSONA, 0, "f")
    lines = [first]
    for turn in range(1, 6):
        nxt = template_line(resp, PERSONA, turn, "f", previous_line=lines[-1])
        assert nxt != lines[-1]
        assert guard_child_line(nxt, resp)[0], nxt
        lines.append(nxt)
    print(f"RAVI {kind.value}:", " | ".join(lines[:3]))


def test_without_a_previous_line_nothing_changes() -> None:
    assert template_line(_resp(ResponseKind.ANSWER), PERSONA) == "45!"


@pytest.mark.asyncio
async def test_prompt_has_previous_line_and_the_instruction() -> None:
    seen: list[dict[str, Any]] = []

    async def fake(**kwargs: Any) -> dict[str, str]:
        seen.append(kwargs)
        return {"line_hi": "मुझे समझ नहीं आया, मैं तो 7 में से 2 घटाता हूँ। उत्तर 45 है!"}

    prev = "तो 7 में से 2 घटाया, 5 आया। उत्तर 45 है!"
    with patch("backend.app.llm.roles.child_voice.call_tool", new=AsyncMock(side_effect=fake)):
        line = await voice_child_line(
            _resp(ResponseKind.EXPLAIN_BUG),
            PERSONA,
            previous_line=prev,
            teacher_said="बड़े अंक से बड़ा घटाओ, छोटे अंक के लिए दहाई से उधार लो",
        )
    system, user = seen[0]["system"], seen[0]["messages"][0]["content"]
    assert prev in system and "Do not repeat it" in system and "same mistake" in system
    assert "उधार लो" in user
    assert line != prev


@pytest.mark.asyncio
async def test_identical_model_line_is_retried_then_falls_back_to_a_different_template() -> None:
    prev = "तो 7 में से 2 गया 5। 45!"
    same = {"line_hi": prev}
    with patch("backend.app.llm.roles.child_voice.call_tool", new=AsyncMock(return_value=same)) as m:
        line = await voice_child_line(_resp(ResponseKind.EXPLAIN_BUG), PERSONA, previous_line=prev)
    assert m.call_count == 2
    assert line != prev and "45" in line
    assert guard_child_line(line, _resp(ResponseKind.EXPLAIN_BUG))[0]
