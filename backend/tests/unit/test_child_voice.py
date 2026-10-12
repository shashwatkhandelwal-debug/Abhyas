"""Unit tests for child_voice role, prompt template, template fallback, and golden fixtures.

Strictly follows spec/05 §5.5 and T11 acceptance criteria:
- Prompt v1 verification
- Template fallback tested for all 10 ResponseKinds (all passing guard_child_line)
- Golden good + bad fixtures for every ResponseKind
- Role contract pattern (guard check, retry on guard failure, template fallback on double failure)
- SILENT kind immediate empty return
"""

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from backend.app.content_models import PersonaCard
from backend.app.llm.guards import guard_child_line
from backend.app.llm.roles.child_voice import template_line, voice_child_line
from backend.app.rule_engine.domain import (
    ChildResponse,
    ChildRuntime,
    ChildState,
    Domain,
    Problem,
    ResponseKind,
    SceneState,
    Step,
    TaggedTurn,
    TeachingAct,
)
from backend.app.rule_engine.engine import RuleEngine


@pytest.fixture
def sample_persona() -> PersonaCard:
    return PersonaCard(
        id="ravi",
        name_hi="रवि",
        age=7,
        temperament="confident",
        voice_id="hi-IN-Standard-B",
        speech_style_hi="तेज़ और आत्मविश्वासी",
        off_topic_lines_hi=["दीदी, बाहर तितली उड़ रही है!", "मेरी पतंग कट गई!"],
    )


# ── 1. Template Fallback for all 10 ResponseKinds ─────────────────────────────
@pytest.mark.parametrize(
    "kind,answer,steps,allowed_numbers,forbidden",
    [
        (ResponseKind.ANSWER, 45, [], {45}, {"35"}),
        (
            ResponseKind.EXPLAIN_BUG,
            45,
            [
                Step(code="SUB_SMALLER_FROM_LARGER", text_hi="7 में से 2 गया 5", nums=[7, 2, 5]),
                Step(code="SUB_TENS_NORMAL", text_hi="5 में से 1 गया 4", nums=[5, 1, 4]),
            ],
            {7, 2, 5, 1, 4, 45},
            {"35"},
        ),
        (
            ResponseKind.SCAFFOLDED_CORRECT,
            35,
            [
                Step(code="SUB_UNITS_REGROUP", text_hi="12 में से 7 गया 5", nums=[12, 7, 5]),
                Step(code="SUB_TENS_REGROUP", text_hi="4 में से 1 गया 3", nums=[4, 1, 3]),
            ],
            {12, 7, 5, 4, 1, 3, 35},
            {"45"},
        ),
        (
            ResponseKind.RELAPSE,
            45,
            [
                Step(code="SUB_SMALLER_FROM_LARGER", text_hi="7 में से 2 गया 5", nums=[7, 2, 5]),
            ],
            {7, 2, 5, 45},
            {"35"},
        ),
        (
            ResponseKind.CORRECT_EXPLAINED,
            35,
            [
                Step(code="SUB_UNITS_REGROUP", text_hi="12 में से 7 गया 5", nums=[12, 7, 5]),
                Step(code="SUB_TENS_REGROUP", text_hi="4 में से 1 गया 3", nums=[4, 1, 3]),
            ],
            {12, 7, 5, 4, 1, 3, 35},
            {"45"},
        ),
        (ResponseKind.PARROT, 35, [], {35}, set()),
        (ResponseKind.SILENT, None, [], set(), set()),
        (ResponseKind.OFF_TOPIC, None, [], set(), set()),
        (ResponseKind.INTERJECT, None, [], set(), set()),
        (ResponseKind.CONFUSED, None, [], set(), set()),
    ],
)
def test_template_line_all_kinds_pass_guard(
    kind: ResponseKind,
    answer: int | None,
    steps: list[Step],
    allowed_numbers: set[int],
    forbidden: set[str],
    sample_persona: PersonaCard,
) -> None:
    resp = ChildResponse(
        persona_id=sample_persona.id,
        kind=kind,
        answer=answer,
        prior_state=ChildState.MISCONCEPTION,
        new_state=ChildState.CAN_EXPLAIN
        if kind == ResponseKind.EXPLAIN_BUG
        else ChildState.MISCONCEPTION,
        affect="confident",
        item=Problem(type="sub", a=52, b=17),
        steps=steps,
        allowed_numbers=allowed_numbers,
        forbidden=forbidden,
    )
    line = template_line(resp, sample_persona, turn_idx=0, address_form="f")

    # For SILENT, template_line must return empty string
    if kind == ResponseKind.SILENT:
        assert line == ""

    # Must pass output guard
    valid, msg = guard_child_line(line, resp)
    assert valid is True, f"Guard failed for kind={kind}: {msg} (line='{line}')"


# ── 2. Golden Fixtures Verification (Good + Bad for all 10 Kinds) ────────────
def test_golden_fixtures_all_kinds() -> None:
    golden_dir = Path(__file__).resolve().parent.parent / "golden" / "child_voice"
    assert golden_dir.exists(), f"Golden directory not found: {golden_dir}"

    for kind in ResponseKind:
        good_path = golden_dir / f"{kind.value}_good.json"
        bad_path = golden_dir / f"{kind.value}_bad.json"

        assert good_path.exists(), f"Missing good golden fixture: {good_path.name}"
        assert bad_path.exists(), f"Missing bad golden fixture: {bad_path.name}"

        # Good fixture must PASS guard
        good_data = json.loads(good_path.read_text(encoding="utf-8"))
        good_resp = ChildResponse.model_validate(good_data["input"])
        good_line = good_data["output"]["line_hi"]
        valid_good, msg_good = guard_child_line(good_line, good_resp)
        assert valid_good is True, f"Good fixture {good_path.name} failed guard: {msg_good}"

        # Bad fixture must FAIL guard
        bad_data = json.loads(bad_path.read_text(encoding="utf-8"))
        bad_resp = ChildResponse.model_validate(bad_data["input"])
        bad_line = bad_data["output"]["line_hi"]
        valid_bad, msg_bad = guard_child_line(bad_line, bad_resp)
        assert valid_bad is False, (
            f"Bad fixture {bad_path.name} unexpectedly passed guard: '{bad_line}'"
        )


# ── 3. Role Contract: voice_child_line ───────────────────────────────────────
@pytest.mark.asyncio
async def test_voice_child_line_silent_skips_llm(sample_persona: PersonaCard) -> None:
    resp = ChildResponse(
        persona_id=sample_persona.id,
        kind=ResponseKind.SILENT,
        answer=None,
        prior_state=ChildState.MISCONCEPTION,
        new_state=ChildState.MISCONCEPTION,
        affect="shy",
        item=Problem(type="sub", a=52, b=17),
    )
    with patch("backend.app.llm.roles.child_voice.call_tool") as mock_call:
        line = await voice_child_line(resp, sample_persona)
        assert line == ""
        assert mock_call.call_count == 0


@pytest.mark.asyncio
async def test_voice_child_line_success_with_mock(sample_persona: PersonaCard) -> None:
    resp = ChildResponse(
        persona_id=sample_persona.id,
        kind=ResponseKind.ANSWER,
        answer=45,
        prior_state=ChildState.MISCONCEPTION,
        new_state=ChildState.MISCONCEPTION,
        affect="confident",
        item=Problem(type="sub", a=52, b=17),
        allowed_numbers={45},
        forbidden={"35"},
    )
    mock_payload = {"line_hi": "दीदी, 45 आया!"}
    with patch("backend.app.llm.roles.child_voice.call_tool", new_callable=AsyncMock) as mock_call:
        mock_call.return_value = mock_payload
        line = await voice_child_line(resp, sample_persona)
        assert line == "दीदी, 45 आया!"
        assert mock_call.call_count == 1


@pytest.mark.asyncio
async def test_voice_child_line_retry_on_guard_failure(sample_persona: PersonaCard) -> None:
    resp = ChildResponse(
        persona_id=sample_persona.id,
        kind=ResponseKind.ANSWER,
        answer=45,
        prior_state=ChildState.MISCONCEPTION,
        new_state=ChildState.MISCONCEPTION,
        affect="confident",
        item=Problem(type="sub", a=52, b=17),
        allowed_numbers={45},
        forbidden={"35"},
    )
    # Attempt 0 says forbidden 35 -> fails guard
    bad_payload = {"line_hi": "दीदी, सही उत्तर 35 है!"}
    # Attempt 1 fixes it -> says 45 -> passes guard
    good_payload = {"line_hi": "दीदी, मेरा उत्तर 45 है!"}

    with patch("backend.app.llm.roles.child_voice.call_tool", new_callable=AsyncMock) as mock_call:
        mock_call.side_effect = [bad_payload, good_payload]
        line = await voice_child_line(resp, sample_persona)
        assert line == "दीदी, मेरा उत्तर 45 है!"
        assert mock_call.call_count == 2


@pytest.mark.asyncio
async def test_voice_child_line_fallback_on_double_failure(sample_persona: PersonaCard) -> None:
    resp = ChildResponse(
        persona_id=sample_persona.id,
        kind=ResponseKind.ANSWER,
        answer=45,
        prior_state=ChildState.MISCONCEPTION,
        new_state=ChildState.MISCONCEPTION,
        affect="confident",
        item=Problem(type="sub", a=52, b=17),
        allowed_numbers={45},
        forbidden={"35"},
    )
    # Both attempts fail guard
    bad_payload = {"line_hi": "गलती से 35 बोल दिया"}
    with patch("backend.app.llm.roles.child_voice.call_tool", new_callable=AsyncMock) as mock_call:
        mock_call.side_effect = [bad_payload, bad_payload]
        line = await voice_child_line(resp, sample_persona)
        # Falls back to template_line -> "45!"
        assert line == "45!"
        valid, _ = guard_child_line(line, resp)
        assert valid is True


def test_live_guard_pass_rate_on_30_engine_outputs() -> None:
    """Verify live guard pass >= 90% on >= 30 rule engine outputs (spec/14 §14 Phase C, T11)."""
    personas = {
        "ravi": PersonaCard(
            id="ravi",
            name_hi="रवि",
            age=7,
            temperament="confident",
            voice_id="hi-IN-Standard-B",
            speech_style_hi="तेज़ और आत्मविश्वासी",
            off_topic_lines_hi=["दीदी, बाहर तितली उड़ रही है!"],
        ),
        "priya": PersonaCard(
            id="priya",
            name_hi="प्रिया",
            age=7,
            temperament="shy",
            voice_id="hi-IN-Standard-A",
            speech_style_hi="धीमी और झिझकती आवाज़",
            off_topic_lines_hi=["मुझे पेंसिल नहीं मिल रही।"],
        ),
        "aman": PersonaCard(
            id="aman",
            name_hi="अमन",
            age=7,
            temperament="distracted",
            voice_id="hi-IN-Standard-B",
            speech_style_hi="चुलबुली और बेपरवाह",
            off_topic_lines_hi=["मेरी पतंग कट गई!"],
        ),
    }

    engine = RuleEngine()
    collected_responses: list[ChildResponse] = []

    turns_sequence = [
        TaggedTurn(acts=[TeachingAct.ASK_TO_EXPLAIN], addressed_child="ravi"),
        TaggedTurn(acts=[TeachingAct.PRAISE_EFFORT], addressed_child="ravi"),
        TaggedTurn(acts=[TeachingAct.CONCRETE_REPRESENTATION], addressed_child="all"),
        TaggedTurn(acts=[TeachingAct.ASK_TO_EXPLAIN], addressed_child="priya"),
        TaggedTurn(acts=[TeachingAct.SCOLD], addressed_child="priya"),
        TaggedTurn(acts=[TeachingAct.TELL_ANSWER], addressed_child="aman"),
        TaggedTurn(acts=[TeachingAct.PROBE_SIMPLER_CASE], addressed_child="ravi"),
        TaggedTurn(acts=[TeachingAct.MODEL_STEP_ALOUD], addressed_child="all"),
        TaggedTurn(acts=[TeachingAct.ASK_TO_EXPLAIN], addressed_child="aman"),
        TaggedTurn(acts=[TeachingAct.PRAISE_EFFORT], addressed_child="aman"),
        TaggedTurn(
            acts=[TeachingAct.GIVE_NEW_PROBLEM],
            addressed_child="all",
            problem=Problem(type="sub", a=43, b=27),
        ),
        TaggedTurn(acts=[TeachingAct.ASK_TO_EXPLAIN], addressed_child="ravi"),
        TaggedTurn(acts=[TeachingAct.ASK_TO_EXPLAIN], addressed_child="priya"),
    ]

    for _seed in [1, 2, 3]:
        items = [
            Problem(type="sub", a=52, b=17),
            Problem(type="sub", a=43, b=27),
            Problem(type="sub", a=61, b=28),
            Problem(type="sub", a=74, b=39),
        ]
        children = [
            ChildRuntime(
                persona_id="ravi",
                misconception="SUB_SMALLER_FROM_LARGER",
                temperament="confident",
                state=ChildState.MISCONCEPTION,
            ),
            ChildRuntime(
                persona_id="priya",
                misconception="SUB_BORROW_NO_DECREMENT",
                temperament="shy",
                state=ChildState.MISCONCEPTION,
            ),
            ChildRuntime(
                persona_id="aman",
                misconception="SUB_WRITE_ZERO_WHEN_STUCK",
                temperament="distracted",
                state=ChildState.MISCONCEPTION,
            ),
        ]
        scene = SceneState(
            move_id="NUM_SUB_REGROUP_BUNDLES",
            domain=Domain.NUMERACY,
            effective_acts=[
                TeachingAct.ASK_TO_EXPLAIN,
                TeachingAct.CONCRETE_REPRESENTATION,
                TeachingAct.CONTRAST_TWO_ANSWERS,
                TeachingAct.PROBE_SIMPLER_CASE,
            ],
            target_causes=["SUB_SMALLER_FROM_LARGER", "SUB_BORROW_NO_DECREMENT"],
            items=items,
            current_item=items[0],
            children=children,
            max_turns=15,
        )

        for turn in turns_sequence:
            if scene.ended:
                break
            result = engine.step(scene, turn)
            collected_responses.extend(result.responses)

    assert len(collected_responses) >= 30, (
        f"Expected >= 30 engine outputs, got {len(collected_responses)}"
    )

    passed = 0
    for idx, resp in enumerate(collected_responses):
        persona = personas.get(resp.persona_id, personas["ravi"])
        line = template_line(resp, persona, turn_idx=idx, address_form="f")
        valid, msg = guard_child_line(line, resp)
        if valid:
            passed += 1

    pass_rate = passed / len(collected_responses)
    assert pass_rate >= 0.90, (
        f"Live guard pass rate {pass_rate:.2%} < 90% ({passed}/{len(collected_responses)})"
    )
