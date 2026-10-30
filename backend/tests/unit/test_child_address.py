"""F1: the child addresses the teacher in one right form: दीदी (she), सर (he), none (unknown)."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from backend.app.content_models import PersonaCard
from backend.app.llm.address import address_rule, fix_address
from backend.app.llm.roles.child_voice import template_line, voice_child_line
from backend.app.rule_engine.domain import ChildResponse, ChildState, Problem, ResponseKind, Step

PERSONA = PersonaCard(
    id="ravi",
    name_hi="रवि",
    age=7,
    temperament="confident",
    voice_id="child_ravi",
    speech_style_hi="जल्दी और पूरे भरोसे से बोलता है",
    off_topic_lines_hi=["दीदी, आज खेल का पीरियड होगा?", "दीदी, छुट्टी कब होगी?"],
)


def _resp(kind: ResponseKind = ResponseKind.EXPLAIN_BUG) -> ChildResponse:
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
    ("line", "form", "expected"),
    [
        ("दीदी, सर, तो 7 में से 2 घटाया, 5 आया। उत्तर 45 है!", "f", "दीदी, तो 7 में से 2 घटाया, 5 आया। उत्तर 45 है!"),
        ("दीदी, सर, तो 7 में से 2 घटाया, 5 आया। उत्तर 45 है!", "m", "सर, तो 7 में से 2 घटाया, 5 आया। उत्तर 45 है!"),
        ("दीदी/सर, उत्तर 45 है!", "m", "सर, उत्तर 45 है!"),
        ("दीदी, सर, उत्तर 45 है!", None, "उत्तर 45 है!"),
        ("दीदी सर उत्तर 45 है!", "f", "दीदी उत्तर 45 है!"),
        ("दीदी, सुनो! तो 5 आया।", "m", "सर, सुनो! तो 5 आया।"),
        ("सर, सुनो! तो 5 आया।", "f", "दीदी, सुनो! तो 5 आया।"),
        ("दीदी, सुनो! तो 5 आया।", "", "सुनो! तो 5 आया।"),
        ("मैडम, 45 आया।", "m", "सर, 45 आया।"),
        ("ठीक है दीदी।", None, "ठीक है।"),
        ("सरल है, 45 आया। सरकार!", "f", "सरल है, 45 आया। सरकार!"),
        ("45 आया!", "m", "45 आया!"),
    ],
)
def test_fix_address(line: str, form: str | None, expected: str) -> None:
    assert fix_address(line, form) == expected


def test_rules_state_the_form() -> None:
    assert '"दीदी"' in address_rule("f") and "Never" in address_rule("f")
    assert '"सर"' in address_rule("m")
    assert "Do NOT use any address word" in address_rule(None)


@pytest.mark.parametrize("form", ["f", "m", None])
@pytest.mark.parametrize("kind", [ResponseKind.EXPLAIN_BUG, ResponseKind.OFF_TOPIC, ResponseKind.CONFUSED])
def test_template_path_has_one_form(form: str | None, kind: ResponseKind) -> None:
    line = template_line(_resp(kind), PERSONA, 0, form)
    if kind != ResponseKind.EXPLAIN_BUG:
        assert ("सर," in line) == (form == "m")
    if form != "f":
        assert "दीदी" not in line
    if form != "m":
        assert "सर" not in line
    if form is None:
        assert not line.startswith(",")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("form", "word"), [("f", "दीदी"), ("m", "सर"), (None, "")]
)
async def test_model_path_prompt_has_the_rule_and_the_line_is_fixed(
    form: str | None, word: str
) -> None:
    seen: dict[str, Any] = {}

    async def fake(**kwargs: Any) -> dict[str, str]:
        seen.update(kwargs)
        return {"line_hi": "दीदी, सर, तो 7 में से 2 घटाया, 5 आया। उत्तर 45 है!"}

    with patch("backend.app.llm.roles.child_voice.call_tool", new=AsyncMock(side_effect=fake)):
        line = await voice_child_line(_resp(), PERSONA, address_form=form)
    assert address_rule(form) in seen["system"]
    assert "दीदी, सर" not in line and "दीदी/सर" not in line
    assert line.startswith(f"{word}, तो" if word else "तो")
    print(f"MOCK form={form!r}: {line}")


@pytest.mark.asyncio
@pytest.mark.parametrize("form", ["f", "m", None])
async def test_onboarding_scene_uses_the_same_prompt_rule(form: str | None) -> None:
    """The onboarding practice scene (52 - 17, Ravi) goes through the same voice_child_line."""
    seen: dict[str, Any] = {}

    async def fake(**kwargs: Any) -> dict[str, str]:
        seen.update(kwargs)
        return {"line_hi": "दीदी, सुनो! तो 7 में से 2 घटाया, 5 आया। उत्तर 45 है!"}

    with patch("backend.app.llm.roles.child_voice.call_tool", new=AsyncMock(side_effect=fake)):
        line = await voice_child_line(_resp(), PERSONA, address_form=form)
    assert address_rule(form) in seen["system"]
    assert ("सर" in line) == (form == "m") and ("दीदी" in line) == (form == "f")
    print(f"ONBOARDING form={form!r}: {line}")
