"""Part 0: out-of-scope problems and placeholder leaks never reach a child's spoken line."""

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from backend.app.config import settings
from backend.app.content_models import PersonaCard
from backend.app.llm.guards import find_placeholder_leak, guard_child_line
from backend.app.llm.roles.child_voice import voice_child_line
from backend.app.rehearsal.scene_runner import SceneRunner
from backend.app.rehearsal.scene_store import InMemorySceneStore
from backend.app.rehearsal.stt_hints import scene_child_name_hints
from backend.app.rule_engine.domain import (
    ChildResponse,
    ChildRuntime,
    ChildState,
    Domain,
    Problem,
    ResponseKind,
    SceneState,
    TaggedTurn,
    TeachingAct,
)
from backend.app.rule_engine.engine import RuleEngine, _validate_problem

PERSONA = PersonaCard(
    id="ravi",
    name_hi="रवि",
    age=7,
    temperament="confident",
    voice_id="hi-IN-Standard-B",
    speech_style_hi="तेज़",
    off_topic_lines_hi=["दीदी, बाहर तितली उड़ रही है!"],
)


def _confused() -> ChildResponse:
    return ChildResponse(
        persona_id="ravi",
        kind=ResponseKind.CONFUSED,
        answer=None,
        prior_state=ChildState.MISCONCEPTION,
        new_state=ChildState.MISCONCEPTION,
        affect="neutral",
        item=Problem(type="sub", a=52, b=17),
    )


def _scene() -> SceneState:
    return SceneState(
        move_id="M",
        domain=Domain.NUMERACY,
        effective_acts=[TeachingAct.ASK_TO_EXPLAIN],
        target_causes=["SUB_SMALLER_FROM_LARGER"],
        items=[Problem(type="sub", a=52, b=17)],
        current_item=Problem(type="sub", a=52, b=17),
        children=[
            ChildRuntime(
                persona_id="ravi",
                misconception="SUB_SMALLER_FROM_LARGER",
                temperament="confident",
                state=ChildState.MISCONCEPTION,
            )
        ],
    )


def test_three_digit_problem_is_confused_with_no_answer() -> None:
    scene = _scene()
    res = RuleEngine.step(
        scene,
        TaggedTurn(acts=[], addressed_child="ravi", problem=Problem(type="sub", a=200, b=120)),
    )
    resp = res.responses[0]
    assert resp.kind == ResponseKind.CONFUSED
    assert resp.answer is None
    assert scene.children[0].state == ChildState.MISCONCEPTION
    assert scene.current_item.key() == "sub:52-17"  # the item did not change


def test_problem_limits_come_from_config(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _validate_problem(Problem(type="sub", a=99, b=10), Domain.NUMERACY)
    assert not _validate_problem(Problem(type="sub", a=100, b=10), Domain.NUMERACY)
    monkeypatch.setattr(settings, "PROBLEM_MAX_OPERAND", 999)
    assert _validate_problem(Problem(type="sub", a=200, b=120), Domain.NUMERACY)


@pytest.mark.asyncio
async def test_confused_is_voiced_without_llm_or_placeholders() -> None:
    with patch("backend.app.llm.roles.child_voice.call_tool", new_callable=AsyncMock) as call:
        line = await voice_child_line(_confused(), PERSONA)
    call.assert_not_called()
    assert line
    assert find_placeholder_leak(line) is None


@pytest.mark.asyncio
async def test_prompt_never_contains_placeholders() -> None:
    resp = ChildResponse(
        persona_id="ravi",
        kind=ResponseKind.OFF_TOPIC,
        answer=None,
        prior_state=ChildState.MISCONCEPTION,
        new_state=ChildState.MISCONCEPTION,
        affect="distracted",
        item=Problem(type="sub", a=52, b=17),
    )
    with patch("backend.app.llm.roles.child_voice.call_tool", new_callable=AsyncMock) as call:
        call.return_value = {"line_hi": "दीदी, तितली!"}
        await voice_child_line(resp, PERSONA)
    system = call.call_args.kwargs["system"]
    assert "कोई कदम नहीं" not in system
    assert "(none)" not in system
    assert "None" not in system
    assert "{" not in system


@pytest.mark.parametrize(
    "line",
    [
        "दीदी, जवाब None है!",
        "कोई कदम नहीं, जवाब 45 है!",
        "दीदी (none) आया",
        "जवाब null है",
        "दीदी {answer} आया",
        "दीदी 45 }",
    ],
)
def test_guard_rejects_placeholder_leaks(line: str) -> None:
    resp = ChildResponse(
        persona_id="ravi",
        kind=ResponseKind.ANSWER,
        answer=45,
        prior_state=ChildState.MISCONCEPTION,
        new_state=ChildState.MISCONCEPTION,
        affect="confident",
        item=Problem(type="sub", a=52, b=17),
        allowed_numbers={45},
    )
    ok, why = guard_child_line(line, resp)
    assert not ok
    assert "placeholder" in why


@pytest.mark.asyncio
async def test_leaky_model_line_falls_back_to_template() -> None:
    resp = ChildResponse(
        persona_id="ravi",
        kind=ResponseKind.ANSWER,
        answer=45,
        prior_state=ChildState.MISCONCEPTION,
        new_state=ChildState.MISCONCEPTION,
        affect="confident",
        item=Problem(type="sub", a=52, b=17),
        allowed_numbers={45},
        forbidden={"35"},
    )
    with patch("backend.app.llm.roles.child_voice.call_tool", new_callable=AsyncMock) as call:
        call.return_value = {"line_hi": "कोई कदम नहीं, जवाब None है 45!"}
        line = await voice_child_line(resp, PERSONA)
    assert call.call_count == 2  # one retry
    assert line == "45!"


@pytest.mark.asyncio
async def test_stt_hints_are_the_scene_child_names() -> None:
    store = InMemorySceneStore()
    runner = SceneRunner(store=store)  # type: ignore[arg-type]
    teacher = uuid.uuid4()
    assert await scene_child_name_hints(teacher) == []
    with patch("backend.app.rehearsal.stt_hints.scene_store", store):
        assert await scene_child_name_hints(teacher) == []
        await runner.create_scene(teacher)
        names = await scene_child_name_hints(teacher)
    assert set(names) == {"रवि", "प्रिया", "अमन"}


@pytest.mark.parametrize(
    "line", ["दीदी, 3 आया... अरे मेरा बस्ता कहाँ गया... तो 45!", "दीदी, 45! पेंसिल गिर गई।"]
)
def test_guard_rejects_a_digression_in_a_lesson_answer(line: str) -> None:
    resp = ChildResponse(
        persona_id="aman",
        kind=ResponseKind.ANSWER,
        answer=45,
        prior_state=ChildState.MISCONCEPTION,
        new_state=ChildState.MISCONCEPTION,
        affect="distracted",
        item=Problem(type="sub", a=52, b=17),
        allowed_numbers={45, 3},
    )
    ok, why = guard_child_line(line, resp)
    assert not ok and "digress" in why


def test_an_engine_chosen_off_topic_line_may_digress() -> None:
    resp = ChildResponse(
        persona_id="aman",
        kind=ResponseKind.OFF_TOPIC,
        answer=None,
        prior_state=ChildState.MISCONCEPTION,
        new_state=ChildState.MISCONCEPTION,
        affect="distracted",
        item=Problem(type="sub", a=52, b=17),
    )
    assert guard_child_line("दीदी, मेरी पेंसिल गिर गई!", resp)[0]
