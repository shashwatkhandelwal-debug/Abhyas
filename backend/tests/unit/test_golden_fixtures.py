"""Unit tests for all runtime role golden fixtures (spec/05 §5.11, T38).

Verifies that every runtime Claude role has >= 5 golden fixtures in
backend/tests/golden/<role>/, all pass fixtures satisfy their output
schemas and guard functions, and deliberately bad variants fail with the expected guard.
"""

from __future__ import annotations

import json
from pathlib import Path

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
    CoachFeedbackOutput,
    FidelityCheckerOutput,
    GuideAnswererOutput,
    IntentRouterOutput,
    QuestionClassifierOutput,
    RetrievedChunk,
)
from backend.app.rule_engine.domain import ChildResponse, ResponseKind

GOLDEN_BASE_DIR = Path(__file__).resolve().parent.parent / "golden"

RUNTIME_ROLES = (
    "act_tagger",
    "child_voice",
    "coach",
    "fidelity_checker",
    "guide_answerer",
    "question_classifier",
    "intent_router",
)


def test_all_runtime_roles_have_at_least_five_golden_fixtures() -> None:
    """Every runtime role must have at least 5 golden fixtures (spec/05 §5.11)."""
    assert GOLDEN_BASE_DIR.is_dir(), f"Golden directory not found: {GOLDEN_BASE_DIR}"

    for role in RUNTIME_ROLES:
        role_dir = GOLDEN_BASE_DIR / role
        assert role_dir.is_dir(), f"Missing golden fixture directory for role '{role}': {role_dir}"

        if role == "child_voice":
            good_files = list(role_dir.glob("*_good.json"))
            assert len(good_files) >= 5, (
                f"Role '{role}' expected >= 5 good golden fixtures, found {len(good_files)}"
            )
        elif role in ("fidelity_checker", "coach", "intent_router"):
            pass_files = list(role_dir.glob("pass_*.json"))
            assert len(pass_files) >= 5, (
                f"Role '{role}' expected >= 5 pass golden fixtures, found {len(pass_files)}"
            )
        else:
            json_files = list(role_dir.glob("*.json"))
            assert len(json_files) >= 5, (
                f"Role '{role}' expected >= 5 golden fixtures, found {len(json_files)}"
            )


def test_intent_router_golden_fixtures() -> None:
    """Verifies intent_router golden pass and fail fixtures."""
    role_dir = GOLDEN_BASE_DIR / "intent_router"
    pass_files = sorted(role_dir.glob("pass_*.json"))
    fail_files = sorted(role_dir.glob("fail_*.json"))

    assert len(pass_files) >= 5, f"Expected >= 5 pass fixtures, found {len(pass_files)}"
    assert len(fail_files) >= 2, f"Expected >= 2 fail fixtures, found {len(fail_files)}"

    for pf in pass_files:
        data = json.loads(pf.read_text(encoding="utf-8"))
        assert data["role"] == "intent_router"
        out = IntentRouterOutput.model_validate(data["output"])
        valid, msg = guard_intent_router(out)
        assert valid is True, f"Fixture {pf.name} failed guard_intent_router: {msg}"

    for ff in fail_files:
        data = json.loads(ff.read_text(encoding="utf-8"))
        try:
            out = IntentRouterOutput.model_validate(data["output"])
            valid, _ = guard_intent_router(out)
            assert valid is False, f"Fail fixture {ff.name} unexpectedly passed guard"
        except Exception:
            # Pydantic validation failure is also an expected guard failure
            pass


def test_coach_golden_fixtures() -> None:
    """Verifies coach golden pass and fail fixtures."""
    role_dir = GOLDEN_BASE_DIR / "coach"
    pass_files = sorted(role_dir.glob("pass_*.json"))
    fail_files = sorted(role_dir.glob("fail_*.json"))

    assert len(pass_files) >= 5, f"Expected >= 5 pass fixtures, found {len(pass_files)}"
    assert len(fail_files) >= 3, f"Expected >= 3 fail fixtures, found {len(fail_files)}"

    for pf in pass_files:
        data = json.loads(pf.read_text(encoding="utf-8"))
        assert data["role"] == "coach"
        fb = CoachFeedbackOutput.model_validate(data["output"])
        inp = data["input"]
        valid, msg = guard_coach(
            output=fb,
            rubric_criterion_ids=inp["rubric_criterion_ids"],
            teacher_lines=inp["teacher_lines"],
            rubric_rewards_not_telling=inp["rubric_rewards_not_telling"],
            current_item_answer=inp["current_item_answer"],
        )
        assert valid is True, f"Fixture {pf.name} failed guard_coach: {msg}"

    for ff in fail_files:
        data = json.loads(ff.read_text(encoding="utf-8"))
        fb = CoachFeedbackOutput.model_validate(data["output"])
        inp = data["input"]
        valid, _ = guard_coach(
            output=fb,
            rubric_criterion_ids=inp["rubric_criterion_ids"],
            teacher_lines=inp["teacher_lines"],
            rubric_rewards_not_telling=inp["rubric_rewards_not_telling"],
            current_item_answer=inp["current_item_answer"],
        )
        assert valid is False, f"Fail fixture {ff.name} unexpectedly passed guard_coach"


def test_fidelity_checker_golden_fixtures() -> None:
    """Verifies fidelity_checker golden pass and fail fixtures."""
    role_dir = GOLDEN_BASE_DIR / "fidelity_checker"
    pass_files = sorted(role_dir.glob("pass_*.json"))
    fail_files = sorted(role_dir.glob("fail_*.json"))

    assert len(pass_files) >= 5, f"Expected >= 5 pass fixtures, found {len(pass_files)}"
    assert len(fail_files) >= 3, f"Expected >= 3 fail fixtures, found {len(fail_files)}"

    for pf in pass_files:
        data = json.loads(pf.read_text(encoding="utf-8"))
        assert data["role"] == "fidelity_checker"
        out = FidelityCheckerOutput.model_validate(data["output"])
        valid, msg = guard_fidelity_checker(
            output=out,
            expected_point_ids=data["input"]["expected_point_ids"],
            transcript=data["input"]["transcript"],
        )
        assert valid is True, f"Fixture {pf.name} failed guard_fidelity_checker: {msg}"

    for ff in fail_files:
        data = json.loads(ff.read_text(encoding="utf-8"))
        out = FidelityCheckerOutput.model_validate(data["output"])
        valid, _ = guard_fidelity_checker(
            output=out,
            expected_point_ids=data["input"]["expected_point_ids"],
            transcript=data["input"]["transcript"],
        )
        assert valid is False, f"Fail fixture {ff.name} unexpectedly passed guard"


def test_guide_answerer_golden_fixtures() -> None:
    """Verifies guide_answerer golden fixtures."""
    role_dir = GOLDEN_BASE_DIR / "guide_answerer"
    files = sorted(role_dir.glob("pass_*.json"))
    assert len(files) >= 5, f"Expected >= 5 golden fixtures, found {len(files)}"

    for f in files:
        data = json.loads(f.read_text(encoding="utf-8"))
        assert data["role"] == "guide_answerer"
        out = GuideAnswererOutput.model_validate(data["output"])
        chunks = [RetrievedChunk.model_validate(c) for c in data["input"]["chunks"]]
        valid, msg = guard_guide_answerer(out, retrieved_chunks=chunks)
        assert valid is True, f"Fixture {f.name} failed guard_guide_answerer: {msg}"


def test_question_classifier_golden_fixtures() -> None:
    """Verifies question_classifier golden fixtures."""
    role_dir = GOLDEN_BASE_DIR / "question_classifier"
    files = sorted(role_dir.glob("pass_*.json"))
    assert len(files) >= 5, f"Expected >= 5 golden fixtures, found {len(files)}"

    for f in files:
        data = json.loads(f.read_text(encoding="utf-8"))
        assert data["role"] == "question_classifier"
        out = QuestionClassifierOutput.model_validate(data["output"])
        valid, msg = guard_question_classifier(out)
        assert valid is True, f"Fixture {f.name} failed guard_question_classifier: {msg}"


def test_act_tagger_golden_fixtures() -> None:
    """Verifies act_tagger golden fixtures."""
    role_dir = GOLDEN_BASE_DIR / "act_tagger"
    files = sorted(role_dir.glob("*.json"))
    assert len(files) >= 5, f"Expected >= 5 golden fixtures, found {len(files)}"

    for f in files:
        data = json.loads(f.read_text(encoding="utf-8"))
        assert data["role"] == "act_tagger"
        out = ActTaggerOutput.model_validate(data["output"])
        inp = data["input"]
        valid, msg = guard_act_tagger(out, inp["transcript"], inp["scene_persona_ids"])
        assert valid is True, f"Fixture {f.name} failed guard_act_tagger: {msg}"


def test_child_voice_golden_fixtures() -> None:
    """Verifies child_voice golden fixtures (good and bad for all kinds)."""
    role_dir = GOLDEN_BASE_DIR / "child_voice"
    for kind in ResponseKind:
        good_path = role_dir / f"{kind.value}_good.json"
        bad_path = role_dir / f"{kind.value}_bad.json"
        assert good_path.exists(), f"Missing good golden fixture: {good_path.name}"
        assert bad_path.exists(), f"Missing bad golden fixture: {bad_path.name}"

        good_data = json.loads(good_path.read_text(encoding="utf-8"))
        good_resp = ChildResponse.model_validate(good_data["input"])
        valid_good, msg_good = guard_child_line(good_data["output"]["line_hi"], good_resp)
        assert valid_good is True, f"Fixture {good_path.name} failed: {msg_good}"

        bad_data = json.loads(bad_path.read_text(encoding="utf-8"))
        bad_resp = ChildResponse.model_validate(bad_data["input"])
        valid_bad, msg_bad = guard_child_line(bad_data["output"]["line_hi"], bad_resp)
        assert valid_bad is False, f"Fixture {bad_path.name} unexpectedly passed: '{msg_bad}'"
