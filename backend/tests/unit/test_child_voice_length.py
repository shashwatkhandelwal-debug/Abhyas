"""Over-long explain/scaffold lines: cap per kind, and cuts must keep the answer."""

from typing import Any
from unittest.mock import patch

import pytest

from backend.app.config import settings
from backend.app.content_models import PersonaCard
from backend.app.llm.guards import child_line_word_cap, guard_child_line
from backend.app.llm.roles import child_voice as child_voice_mod
from backend.app.llm.roles.child_voice import shorten_keeping_required, voice_child_line
from backend.app.rule_engine.domain import ChildResponse, ChildState, Problem, ResponseKind, Step


def _scaffolded() -> ChildResponse:
    return ChildResponse(
        persona_id="ravi",
        kind=ResponseKind.SCAFFOLDED_CORRECT,
        answer=35,
        correct_answer=35,
        steps=[
            Step(code="A", text_hi="12 में से 7 घटाया, 5 आया", nums=[12, 7, 5]),
            Step(code="B", text_hi="4 में से 1 घटाया, 3 आया", nums=[4, 1, 3]),
        ],
        prior_state=ChildState.MISCONCEPTION,
        new_state=ChildState.CAN_EXPLAIN,
        affect="hesitant",
        item=Problem(type="sub", a=52, b=17),
        allowed_numbers={12, 7, 5, 4, 1, 3, 35},
    )


# Shape of the production failures: 31-35 words, answer in the final sentence.
LONG = (
    "हम्म… दीदी, मुझे सोचने दो, मैं धीरे-धीरे करता हूँ। 12 में से 7 घटाया, 5 आया। "
    "फिर बंडल खोला था तो 4 में से 1 घटाया, 3 आया। अब दोनों को मिलाया तो जवाब 35!"
)


@pytest.fixture
def ravi() -> PersonaCard:
    return PersonaCard(
        id="ravi",
        name_hi="रवि",
        age=7,
        temperament="confident",
        voice_id="child_ravi",
        speech_style_hi="तेज़",
        off_topic_lines_hi=["दीदी, बाहर तितली!"],
    )


def test_explaining_kinds_get_the_larger_cap_and_it_is_tts_short() -> None:
    assert child_line_word_cap(ResponseKind.SCAFFOLDED_CORRECT) == 30
    assert child_line_word_cap(ResponseKind.PARROT) == settings.MAX_CHILD_LINE_WORDS == 25
    assert settings.MAX_CHILD_LINE_WORDS_EXPLAIN <= 35


def test_guard_accepts_30_words_for_scaffold_but_not_for_answer_kind() -> None:
    line = "दीदी, " + "12 में से 7 घटाया, 5 आया। 4 में से 1 घटाया, 3 आया। " + "तो 35 आया।"
    padded = line + " " + " ".join(["हाँ"] * (28 - len(line.split())))
    assert 25 < len(padded.split()) <= 30
    assert guard_child_line(padded, _scaffolded())[0]


def test_cut_keeps_the_sentence_with_the_answer() -> None:
    out = shorten_keeping_required(LONG, 30, _scaffolded())
    assert len(out.split()) <= 30
    assert "35" in out
    assert guard_child_line(out, _scaffolded())[0]


@pytest.mark.asyncio
async def test_overlong_line_is_shortened_not_replaced_by_template(ravi: PersonaCard) -> None:
    too_long = LONG + " " + " ".join(["और"] * 10)

    async def fake(**kw: Any) -> dict[str, Any]:
        return {"line_hi": too_long}

    with patch.object(child_voice_mod, "call_tool", fake):
        line = await voice_child_line(_scaffolded(), ravi)
    assert "35" in line
    assert len(line.split()) <= 30
    assert "सोचने दो" in line or "बंडल खोला" in line or "12 में से" in line
