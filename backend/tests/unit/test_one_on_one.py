"""Part 2: the one-on-one engine mode, the one-on-one rubric content and the diagnosis matcher."""

import copy
import uuid
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
import yaml
from pydantic import ValidationError

from backend.app.config import settings
from backend.app.content_models import ONE_ON_ONE_CRITERIA, MoveCard
from backend.app.llm.guards import guard_diagnosis_classifier
from backend.app.llm.schemas import DiagnosisClassifierOutput
from backend.app.rehearsal.diagnosis import (
    Verdict,
    diagnose,
    judge_diagnosis,
    normalize_diagnosis_text,
)
from backend.app.rehearsal.scene_runner import SceneRunner, load_move_card
from backend.app.rehearsal.scene_store import InMemorySceneStore
from backend.app.rule_engine.domain import (
    ChildState,
    Problem,
    ResponseKind,
    SceneState,
    TaggedTurn,
    TeachingAct,
)
from backend.app.rule_engine.engine import RuleEngine
from content.pipeline.validator import ContentValidationError, validate_move

PERSONAS = {"ravi", "priya", "aman"}
NUMERACY_MOVES = ["NUM_SUB_REGROUP_BUNDLES", "NUM_ADD_CARRY_BUNDLES", "NUM_PLACE_VALUE_BUNDLES"]


async def _scene(
    persona: str = "ravi", move_id: str = "NUM_SUB_REGROUP_BUNDLES"
) -> tuple[SceneState, SceneRunner]:
    runner = SceneRunner(store=InMemorySceneStore())  # type: ignore[arg-type]
    record = await runner.create_scene(uuid.uuid4(), move_id, one_on_one_persona=persona)
    return record.scene_state, runner


def _turn(*acts: TeachingAct, problem: Problem | None = None) -> TaggedTurn:
    return TaggedTurn(acts=list(acts), addressed_child=None, problem=problem)


# ── 2.1 engine with one child ────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
@pytest.mark.parametrize("persona", ["ravi", "priya", "aman"])
async def test_create_one_on_one_scene(persona: str) -> None:
    scene, _ = await _scene(persona)
    assert scene.one_on_one
    assert [c.persona_id for c in scene.children] == [persona]
    assert scene.max_turns == settings.MAX_TURNS_ONE_ON_ONE == 10
    assert TeachingAct.INVOLVE_PEER.value not in scene.effective_acts


@pytest.mark.asyncio
async def test_unknown_persona_is_rejected() -> None:
    runner = SceneRunner(store=InMemorySceneStore())  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        await runner.create_scene(uuid.uuid4(), one_on_one_persona="nobody")


@pytest.mark.asyncio
@pytest.mark.parametrize("persona", ["ravi", "priya", "aman"])
async def test_the_single_child_always_responds_and_progresses(persona: str) -> None:
    scene, _ = await _scene(persona)
    child = scene.children[0]
    r1 = RuleEngine.step(scene, _turn(TeachingAct.ASK_TO_EXPLAIN))
    assert [r.persona_id for r in r1.responses] == [persona]
    assert r1.responses[0].kind == ResponseKind.EXPLAIN_BUG
    assert child.state == ChildState.CAN_EXPLAIN
    RuleEngine.step(scene, _turn(TeachingAct.CONCRETE_REPRESENTATION))
    assert child.state == ChildState.PARTIAL
    r3 = RuleEngine.step(scene, _turn(TeachingAct.CONTRAST_TWO_ANSWERS))
    assert child.state == ChildState.CORRECT
    assert r3.responses[0].kind == ResponseKind.CORRECT_EXPLAINED
    assert not r3.ended  # a check on a new problem is still due


@pytest.mark.asyncio
async def test_scene_ends_after_a_check_on_a_new_problem() -> None:
    scene, _ = await _scene("ravi")
    RuleEngine.step(scene, _turn(TeachingAct.ASK_TO_EXPLAIN))
    RuleEngine.step(scene, _turn(TeachingAct.CONCRETE_REPRESENTATION))
    RuleEngine.step(scene, _turn(TeachingAct.CONTRAST_TWO_ANSWERS))
    res = RuleEngine.step(scene, _turn(problem=Problem(type="sub", a=52, b=17)))
    assert res.responses[0].kind == ResponseKind.CORRECT_EXPLAINED
    assert res.responses[0].answer == 35
    assert res.ended and res.end_reason == "all_correct"


@pytest.mark.asyncio
async def test_turn_limit_ends_a_one_on_one_scene() -> None:
    scene, _ = await _scene("ravi")
    res = None
    for _ in range(settings.MAX_TURNS_ONE_ON_ONE):
        assert not scene.ended
        res = RuleEngine.step(scene, _turn(TeachingAct.REPEAT_QUESTION))
    assert res is not None and res.ended and res.end_reason == "turn_limit"


@pytest.mark.asyncio
async def test_one_on_one_does_not_use_the_placement_two_turn_limit() -> None:
    scene, _ = await _scene("ravi")
    RuleEngine.step(scene, _turn(TeachingAct.ASK_TO_EXPLAIN))
    res = RuleEngine.step(scene, _turn(TeachingAct.ASK_TO_EXPLAIN))
    assert not res.ended


@pytest.mark.asyncio
async def test_tell_the_answer_gets_a_parrot_and_no_progress() -> None:
    scene, _ = await _scene("ravi")
    res = RuleEngine.step(scene, _turn(TeachingAct.TELL_ANSWER))
    assert res.responses[0].kind == ResponseKind.PARROT
    assert scene.children[0].state == ChildState.MISCONCEPTION


@pytest.mark.asyncio
async def test_shy_child_silence_after_a_scolding_then_speaks() -> None:
    scene, _ = await _scene("priya")
    assert scene.children[0].temperament == "shy"
    r1 = RuleEngine.step(scene, _turn(TeachingAct.SCOLD))
    assert r1.responses[0].kind == ResponseKind.SILENT
    r2 = RuleEngine.step(scene, _turn(TeachingAct.PRAISE_EFFORT, TeachingAct.ASK_TO_EXPLAIN))
    assert r2.responses[0].kind == ResponseKind.EXPLAIN_BUG


@pytest.mark.asyncio
@pytest.mark.parametrize("max_distractions", [0, 1])
async def test_distraction_limits_with_one_child(
    monkeypatch: pytest.MonkeyPatch, max_distractions: int
) -> None:
    monkeypatch.setattr(settings, "MAX_DISTRACTIONS_PER_SCENE", max_distractions)
    scene, _ = await _scene("aman")
    assert scene.children[0].temperament == "distracted"
    kinds = []
    for _ in range(4):
        res = RuleEngine.step(scene, _turn(TeachingAct.OFF_TASK))
        assert len(res.responses) == 1  # never an interjection from a (non-existent) peer
        kinds.append(res.responses[0].kind)
    off_topic = [k for k in kinds if k == ResponseKind.OFF_TOPIC]
    assert len(off_topic) == max_distractions
    assert scene.distractions_used == max_distractions


@pytest.mark.asyncio
async def test_involve_peer_and_whole_class_acts_do_not_crash_with_one_child() -> None:
    scene, _ = await _scene("ravi")
    for tagged in (
        TaggedTurn(acts=[TeachingAct.INVOLVE_PEER], addressed_child="all"),
        TaggedTurn(acts=[TeachingAct.CONCRETE_REPRESENTATION], addressed_child="all"),
        TaggedTurn(acts=[TeachingAct.ASK_TO_EXPLAIN], addressed_child="priya"),  # not in the scene
    ):
        res = RuleEngine.step(scene, tagged)
        assert [r.persona_id for r in res.responses] == ["ravi"]
    assert scene.children[0].state >= ChildState.PARTIAL


# ── 2.2 content ──────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("move_id", NUMERACY_MOVES)
def test_numeracy_cards_have_the_one_on_one_rubric_and_english_bank(move_id: str) -> None:
    card = load_move_card(move_id)
    assert card.rubric_one_on_one is not None
    assert sorted(c.id for c in card.rubric_one_on_one.criteria) == sorted(ONE_ON_ONE_CRITERIA)
    assert "crit_all_children" not in {c.id for c in card.rubric_one_on_one.criteria}
    for item in card.feedback_bank_one_on_one.values():
        assert item.strength_hi and item.change_en and item.exact_words_en
    view = card.one_on_one_view()
    assert {c.id for c in view.rubric.criteria} == set(ONE_ON_ONE_CRITERIA)
    assert set(view.feedback_bank) == set(ONE_ON_ONE_CRITERIA)
    for child in card.scenario.children:  # every scene misconception can be diagnosed
        assert child.misconception in card.misconceptions
    # The hint lines never give the answer away (they are shown to the teacher as model words)
    assert "does_not_tell_answer" in view.feedback_bank


def _raw(move_id: str) -> dict[str, Any]:
    with open(f"content/moves/{move_id}.yaml", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    assert isinstance(data, dict)
    return data


def test_validator_rejects_a_numeracy_card_without_the_one_on_one_rubric() -> None:
    raw = _raw("NUM_SUB_REGROUP_BUNDLES")
    del raw["rubric_one_on_one"]
    with pytest.raises(ValidationError, match="rubric_one_on_one"):
        MoveCard.model_validate(raw)


def test_validator_rejects_the_involve_all_children_criterion() -> None:
    raw = _raw("NUM_SUB_REGROUP_BUNDLES")
    raw["rubric_one_on_one"]["criteria"][0]["id"] = "crit_all_children"
    with pytest.raises(ValidationError, match="criteria must be"):
        MoveCard.model_validate(raw)


def test_validator_rejects_a_missing_english_line_or_misconception_keywords() -> None:
    raw = _raw("NUM_ADD_CARRY_BUNDLES")
    bad = copy.deepcopy(raw)
    bad["feedback_bank_one_on_one"]["asks_to_explain"]["change_en"] = " "
    with pytest.raises(ValidationError, match="change_en"):
        MoveCard.model_validate(bad)
    bad = copy.deepcopy(raw)
    del bad["misconceptions"]["ADD_NO_CARRY"]
    with pytest.raises(ContentValidationError, match="ADD_NO_CARRY"):
        validate_move(bad, {"nipun_guidelines_2021", "up_ganit_sandarshika_c1"}, PERSONAS)
    bad = copy.deepcopy(raw)
    bad["misconceptions"]["ADD_NO_CARRY"]["keywords"] = []
    with pytest.raises(ValidationError):
        MoveCard.model_validate(bad)


def test_literacy_card_does_not_need_the_one_on_one_rubric() -> None:
    assert load_move_card("LIT_MATRA_BLENDING").rubric_one_on_one is None


# ── 2.3 diagnosis ────────────────────────────────────────────────────────────────────────────
SUB = load_move_card("NUM_SUB_REGROUP_BUNDLES")


def test_verdict_correct_hindi_hinglish_and_english() -> None:
    for text in (
        "रवि ने उल्टा घटा दिया, छोटी संख्या में से बड़ी",
        "bade mein se chhota ghata diya, ulta kiya",
        "He subtracts the smaller digit from the larger one, flipped",
        "३ में से ७ नहीं हुआ तो 7 में से 3 कर दिया",
    ):
        res = judge_diagnosis(text, SUB, "SUB_SMALLER_FROM_LARGER")
        assert res.verdict == Verdict.CORRECT, text
        assert res.matched_misconception == "SUB_SMALLER_FROM_LARGER"


def test_verdict_partly() -> None:
    # topic only: right area (subtraction, units) but no specific mistake named
    res = judge_diagnosis("इकाई में घटाव गलत किया", SUB, "SUB_SMALLER_FROM_LARGER")
    assert res.verdict == Verdict.PARTLY and res.reason == "topic_only"
    # named the true mistake and another one (hedging)
    res = judge_diagnosis("उल्टा घटाया, या शायद शून्य लिख दिया", SUB, "SUB_SMALLER_FROM_LARGER")
    assert res.verdict == Verdict.PARTLY and res.reason == "ambiguous"


def test_verdict_wrong() -> None:
    res = judge_diagnosis("उसने शून्य लिख दिया", SUB, "SUB_SMALLER_FROM_LARGER")
    assert res.verdict == Verdict.WRONG
    assert res.matched_misconception == "SUB_WRITE_ZERO_WHEN_STUCK"
    assert res.reason == "other_misconception"


def test_empty_and_off_topic_text() -> None:
    for text in ("", "   ", "...", None):
        res = judge_diagnosis(text or "", SUB, "SUB_SMALLER_FROM_LARGER")
        assert res.verdict == Verdict.WRONG and res.reason == "empty"
    res = judge_diagnosis("आज मौसम बहुत अच्छा है", SUB, "SUB_SMALLER_FROM_LARGER")
    assert res.verdict == Verdict.WRONG and res.reason == "no_match"


def test_classifier_id_names_a_candidate_but_the_matcher_decides() -> None:
    vague = "उसे समझ नहीं आया कि करना क्या है"
    assert judge_diagnosis(vague, SUB, "SUB_SMALLER_FROM_LARGER").verdict == Verdict.WRONG
    res = judge_diagnosis(
        vague, SUB, "SUB_SMALLER_FROM_LARGER", classified_id="SUB_SMALLER_FROM_LARGER"
    )
    assert res.verdict == Verdict.CORRECT and res.used_classifier
    res = judge_diagnosis(
        vague, SUB, "SUB_SMALLER_FROM_LARGER", classified_id="SUB_BORROW_NO_DECREMENT"
    )
    assert res.verdict == Verdict.WRONG
    # an id that is not a candidate is ignored
    res = judge_diagnosis(vague, SUB, "SUB_SMALLER_FROM_LARGER", classified_id="PV_REVERSAL")
    assert res.verdict == Verdict.WRONG and not res.used_classifier


@pytest.mark.asyncio
async def test_diagnose_skips_the_classifier_when_keywords_decide() -> None:
    with patch(
        "backend.app.rehearsal.diagnosis.classify_diagnosis", new_callable=AsyncMock
    ) as classify:
        res = await diagnose("उल्टा घटा दिया", SUB, "SUB_SMALLER_FROM_LARGER")
    classify.assert_not_called()
    assert res.verdict == Verdict.CORRECT


@pytest.mark.asyncio
async def test_diagnose_asks_the_classifier_only_for_unclear_text() -> None:
    with patch(
        "backend.app.rehearsal.diagnosis.classify_diagnosis", new_callable=AsyncMock
    ) as classify:
        classify.return_value = "SUB_SMALLER_FROM_LARGER"
        res = await diagnose("बच्चा उलझ गया है", SUB, "SUB_SMALLER_FROM_LARGER")
    classify.assert_awaited_once()
    assert res.verdict == Verdict.CORRECT and res.used_classifier


@pytest.mark.asyncio
async def test_diagnose_on_the_mock_llm_falls_back_to_keywords() -> None:
    res = await diagnose("बच्चा उलझ गया है", SUB, "SUB_SMALLER_FROM_LARGER")
    assert res.verdict == Verdict.WRONG  # mock classifier says "none"
    empty = await diagnose("", SUB, "SUB_SMALLER_FROM_LARGER")
    assert empty.reason == "empty"


def test_classifier_guard_rejects_ids_that_were_not_offered() -> None:
    ids = ["A", "B"]
    assert guard_diagnosis_classifier(
        DiagnosisClassifierOutput(misconception_id="A", confidence=1), ids
    )[0]
    assert guard_diagnosis_classifier(
        DiagnosisClassifierOutput(misconception_id="none", confidence=0), ids
    )[0]
    ok, why = guard_diagnosis_classifier(
        DiagnosisClassifierOutput(misconception_id="Z", confidence=1), ids
    )
    assert not ok and "Z" in why


@pytest.mark.asyncio
async def test_classifier_role_retries_once_then_falls_back() -> None:
    from backend.app.llm.roles.diagnosis_classifier import classify_diagnosis

    with patch(
        "backend.app.llm.roles.diagnosis_classifier.call_tool", new_callable=AsyncMock
    ) as ct:
        ct.return_value = {"misconception_id": "NOT_OFFERED", "confidence": 0.9}
        assert await classify_diagnosis("x", {"A": "a"}) is None
        assert ct.call_count == 2
    with patch(
        "backend.app.llm.roles.diagnosis_classifier.call_tool", new_callable=AsyncMock
    ) as ct:
        ct.side_effect = [
            {"misconception_id": "NOT_OFFERED", "confidence": 0.9},
            {"misconception_id": "A", "confidence": 0.9},
        ]
        assert await classify_diagnosis("x", {"A": "a"}) == "A"


def test_normalisation_handles_devanagari_digits_and_punctuation() -> None:
    assert normalize_diagnosis_text("  ७ में से ३, ठीक?  ") == "7 में से 3 ठीक"
