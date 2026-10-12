"""Tests verifying golden fixtures against schemas and guards (spec/05 §5.11, T38)."""

import json
import unicodedata
from pathlib import Path

import pytest
from pydantic import BaseModel, ValidationError

from backend.app.llm.guards import (
    guard_act_tagger,
    guard_child_line,
    guard_coach,
    guard_fidelity_checker,
    guard_guide_answerer,
    guard_intent_router,
    guard_question_classifier,
)
from backend.app.llm.schemas import (
    ActTaggerOutput,
    ChildVoiceOutput,
    CoachFeedbackOutput,
    FidelityCheckerOutput,
    GuideAnswererOutput,
    IntentRouterOutput,
    QuestionClassifierOutput,
)
from backend.app.rule_engine.domain import (
    ChildResponse,
    ChildState,
    Problem,
    ResponseKind,
)

GOLDEN_DIR = Path("backend/tests/golden")

ROLE_SCHEMA_MAP: dict[str, type[BaseModel]] = {
    "intent_router": IntentRouterOutput,
    "act_tagger": ActTaggerOutput,
    "child_voice": ChildVoiceOutput,
    "coach": CoachFeedbackOutput,
    "fidelity_checker": FidelityCheckerOutput,
    "question_classifier": QuestionClassifierOutput,
    "guide_answerer": GuideAnswererOutput,
}


def is_nfc(text: str) -> bool:
    return text == unicodedata.normalize("NFC", text)


@pytest.mark.parametrize("role,schema_cls", list(ROLE_SCHEMA_MAP.items()))
def test_role_golden_fixtures_exist_and_validate(role: str, schema_cls: type[BaseModel]) -> None:
    """Every runtime role must have >= 5 valid fixtures conforming to its pydantic schema."""
    role_dir = GOLDEN_DIR / role
    assert role_dir.exists(), f"Golden directory for role {role} missing: {role_dir}"

    fixtures = list(role_dir.glob("*.json"))
    assert len(fixtures) >= 5, f"Role {role} has {len(fixtures)} fixtures, expected at least 5"

    for fix_path in fixtures:
        with open(fix_path, encoding="utf-8") as f:
            data = json.load(f)

        assert "input" in data, f"Fixture {fix_path.name} missing 'input'"
        assert "output" in data, f"Fixture {fix_path.name} missing 'output'"

        # Schema validation of output
        parsed_output = schema_cls.model_validate(data["output"])
        assert parsed_output is not None

        # Verify NFC normalization on string fields
        for k, v in data["output"].items():
            if isinstance(v, str):
                assert is_nfc(v), f"Output string {k} in {fix_path.name} not NFC"


def test_intent_router_fixtures_pass_guard() -> None:
    """intent_router valid fixtures must satisfy guard_intent_router."""
    role_dir = GOLDEN_DIR / "intent_router"
    for fix_path in role_dir.glob("*.json"):
        with open(fix_path, encoding="utf-8") as f:
            data = json.load(f)

        parsed = IntentRouterOutput.model_validate(data["output"])
        is_valid, reason = guard_intent_router(parsed)
        assert is_valid, f"Fixture {fix_path.name} failed guard: {reason}"


def test_act_tagger_fixtures_pass_guard() -> None:
    """act_tagger valid fixtures must satisfy guard_act_tagger."""
    role_dir = GOLDEN_DIR / "act_tagger"
    for fix_path in role_dir.glob("*.json"):
        with open(fix_path, encoding="utf-8") as f:
            data = json.load(f)

        parsed = ActTaggerOutput.model_validate(data["output"])
        transcript = data["input"]["transcript"]
        scene_persona_ids = ["ravi", "priya", "aman"]

        is_valid, reason = guard_act_tagger(parsed, transcript, scene_persona_ids)
        assert is_valid, f"Fixture {fix_path.name} failed guard: {reason}"


def test_child_voice_fixtures_pass_guard() -> None:
    """Child voice valid fixtures must satisfy guard_child_line guard."""
    role_dir = GOLDEN_DIR / "child_voice"
    for fix_path in role_dir.glob("*.json"):
        with open(fix_path, encoding="utf-8") as f:
            data = json.load(f)

        inp = data["input"]
        out = data["output"]
        line_hi = out["line_hi"]
        assert is_nfc(line_hi), f"Child voice line in {fix_path.name} not NFC"

        resp_data = inp["response"]
        kind = getattr(ResponseKind, resp_data["kind"])

        # Construct ChildResponse domain object
        item_data = resp_data.get("item", {})
        item = Problem(
            type=item_data.get("type", "sub"),
            a=item_data.get("a"),
            b=item_data.get("b"),
        )
        affect_val = resp_data.get("affect", "neutral").lower()
        if affect_val not in (
            "neutral",
            "confident",
            "encouraged",
            "upset",
            "shy",
            "distracted",
        ):
            affect_val = (
                "confident" if inp["persona"].get("temperament") == "confident" else "neutral"
            )

        child_response = ChildResponse(
            persona_id=inp["persona"]["id"],
            kind=kind,
            answer=resp_data.get("answer"),
            steps=[],
            prior_state=ChildState.MISCONCEPTION,
            new_state=ChildState.MISCONCEPTION,
            affect=affect_val,
            item=item,
            allowed_numbers=set(inp.get("allowed_numbers", [])),
            forbidden=set(inp.get("forbidden_numbers", [])),
        )

        is_valid, reason = guard_child_line(line_hi, child_response)
        assert is_valid, f"Fixture {fix_path.name} failed child_voice guard: {reason}"


def test_coach_fixtures_pass_guard() -> None:
    """Coach valid fixtures must satisfy guard_coach guard."""
    role_dir = GOLDEN_DIR / "coach"
    for fix_path in role_dir.glob("*.json"):
        with open(fix_path, encoding="utf-8") as f:
            data = json.load(f)

        transcript = data["input"]["transcript"]
        parsed = CoachFeedbackOutput.model_validate(data["output"])
        criteria_ids = list(parsed.scores.keys())

        is_valid, reason = guard_coach(
            parsed,
            rubric_criterion_ids=criteria_ids,
            teacher_transcript=transcript,
            rubric_rewards_not_telling=True,
            current_item_answer=35,
        )
        assert is_valid, f"Fixture {fix_path.name} failed coach guard: {reason}"


def test_fidelity_checker_fixtures_pass_guard() -> None:
    """Fidelity checker valid fixtures must satisfy guard_fidelity_checker guard."""
    role_dir = GOLDEN_DIR / "fidelity_checker"
    for fix_path in role_dir.glob("*.json"):
        with open(fix_path, encoding="utf-8") as f:
            data = json.load(f)

        transcript = data["input"]["transcript"]
        parsed = FidelityCheckerOutput.model_validate(data["output"])
        kp_ids = [kp["id"] for kp in data["input"]["key_points"]]

        is_valid, reason = guard_fidelity_checker(parsed, transcript, kp_ids)
        assert is_valid, f"Fixture {fix_path.name} failed fidelity guard: {reason}"


def test_question_classifier_fixtures_pass_guard() -> None:
    """question_classifier valid fixtures must satisfy guard_question_classifier guard."""
    role_dir = GOLDEN_DIR / "question_classifier"
    for fix_path in role_dir.glob("*.json"):
        with open(fix_path, encoding="utf-8") as f:
            data = json.load(f)

        parsed = QuestionClassifierOutput.model_validate(data["output"])
        is_valid, reason = guard_question_classifier(parsed)
        assert is_valid, f"Fixture {fix_path.name} failed question_classifier guard: {reason}"


def test_guide_answerer_fixtures_pass_guard() -> None:
    """Guide answerer valid fixtures must satisfy guard_guide_answerer guard."""
    role_dir = GOLDEN_DIR / "guide_answerer"
    for fix_path in role_dir.glob("*.json"):
        with open(fix_path, encoding="utf-8") as f:
            data = json.load(f)

        retrieved_ids = [c["id"] for c in data["input"]["retrieved_chunks"]]
        retrieved_text = " ".join(c["text"] for c in data["input"]["retrieved_chunks"])
        parsed = GuideAnswererOutput.model_validate(data["output"])

        is_valid, reason = guard_guide_answerer(parsed, retrieved_ids, retrieved_text)
        assert is_valid, f"Fixture {fix_path.name} failed guide_answerer guard: {reason}"


def test_bad_variants_fail_schema_or_guards() -> None:
    """Ensure bad variants deliberately violate schema or guard requirements."""
    count = 0
    for role, schema_cls in ROLE_SCHEMA_MAP.items():
        role_dir = GOLDEN_DIR / role
        for fix_path in sorted(role_dir.glob("*.json")):
            with open(fix_path, encoding="utf-8") as f:
                data = json.load(f)
            bad_variants = data.get("bad_variants", [])
            for bad in bad_variants:
                count += 1
                bad_output = bad["output"]
                try:
                    parsed = schema_cls.model_validate(bad_output)
                except ValidationError:
                    # Expected schema error
                    continue

                # If schema passes, guard MUST fail
                inp = data["input"]
                if role == "intent_router":
                    is_valid, _ = guard_intent_router(parsed)  # type: ignore[arg-type]
                    assert not is_valid, (
                        f"Bad variant '{bad['description']}' in {fix_path.name} unexpectedly passed guard"
                    )
                elif role == "act_tagger":
                    transcript = inp.get("transcript", "")
                    scene_personas = inp.get("scene_persona_ids", ["ravi", "priya", "aman"])
                    is_valid, _ = guard_act_tagger(parsed, transcript, scene_personas)  # type: ignore[arg-type]
                    assert not is_valid, (
                        f"Bad variant '{bad['description']}' in {fix_path.name} unexpectedly passed guard"
                    )
                elif role == "child_voice":
                    line_hi = bad_output["line_hi"]
                    resp_data = inp["response"]
                    kind = getattr(ResponseKind, resp_data["kind"])
                    item_data = resp_data.get("item", {})
                    item = Problem(
                        type=item_data.get("type", "sub"),
                        a=item_data.get("a"),
                        b=item_data.get("b"),
                    )
                    affect_val = resp_data.get("affect", "neutral").lower()
                    if affect_val not in (
                        "neutral",
                        "confident",
                        "encouraged",
                        "upset",
                        "shy",
                        "distracted",
                    ):
                        affect_val = (
                            "confident"
                            if inp["persona"].get("temperament") == "confident"
                            else "neutral"
                        )
                    child_response = ChildResponse(
                        persona_id=inp["persona"]["id"],
                        kind=kind,
                        answer=resp_data.get("answer"),
                        steps=[],
                        prior_state=ChildState.MISCONCEPTION,
                        new_state=ChildState.MISCONCEPTION,
                        affect=affect_val,
                        item=item,
                        allowed_numbers=set(inp.get("allowed_numbers", [])),
                        forbidden=set(inp.get("forbidden_numbers", [])),
                    )
                    is_valid, _ = guard_child_line(line_hi, child_response)
                    assert not is_valid, (
                        f"Bad variant '{bad['description']}' in {fix_path.name} unexpectedly passed guard"
                    )
                elif role == "coach":
                    transcript = inp.get("transcript", "")
                    criteria_ids = list(parsed.scores.keys())  # type: ignore[attr-defined]
                    is_valid, _ = guard_coach(
                        parsed,  # type: ignore[arg-type]
                        rubric_criterion_ids=criteria_ids,
                        teacher_transcript=transcript,
                        rubric_rewards_not_telling=True,
                        current_item_answer=35,
                    )
                    assert not is_valid, (
                        f"Bad variant '{bad['description']}' in {fix_path.name} unexpectedly passed guard"
                    )
                elif role == "fidelity_checker":
                    transcript = inp.get("transcript", "")
                    kp_ids = [kp["id"] for kp in inp.get("key_points", [])]
                    is_valid, _ = guard_fidelity_checker(parsed, transcript, kp_ids)  # type: ignore[arg-type]
                    assert not is_valid, (
                        f"Bad variant '{bad['description']}' in {fix_path.name} unexpectedly passed guard"
                    )
                elif role == "question_classifier":
                    is_valid, _ = guard_question_classifier(parsed)  # type: ignore[arg-type]
                    assert not is_valid, (
                        f"Bad variant '{bad['description']}' in {fix_path.name} unexpectedly passed guard"
                    )
                elif role == "guide_answerer":
                    retrieved_ids = [c["id"] for c in inp.get("retrieved_chunks", [])]
                    retrieved_text = " ".join(c["text"] for c in inp.get("retrieved_chunks", []))
                    is_valid, _ = guard_guide_answerer(parsed, retrieved_ids, retrieved_text)  # type: ignore[arg-type]
                    assert not is_valid, (
                        f"Bad variant '{bad['description']}' in {fix_path.name} unexpectedly passed guard"
                    )
    assert count > 0, "No bad variants found"
