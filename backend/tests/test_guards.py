"""Unit tests for Claude output guards (§5.1, §5.3, §6, §8, §9)."""

from backend.app.llm.guards import (
    extract_numbers_from_text,
    normalize_hindi_text,
    validate_child_voice,
    validate_coach_feedback,
)
from backend.app.llm.schemas import CoachFeedbackOutput
from backend.app.rule_engine.child_state import ChildState
from backend.app.rule_engine.engine import RuleEngineResult


def test_extract_numbers():
    assert extract_numbers_from_text("52 mein se 17 kiya to 45 aaya") == [52, 17, 45]
    # Test Devanagari numerals mapping: ५२, १७, ४५
    assert extract_numbers_from_text("५२ mein se १७ to ४५") == [52, 17, 45]


def test_validate_child_voice_authorized_numbers():
    rule_res = RuleEngineResult(
        child_id="ravi",
        child_name="Ravi",
        answer=45,
        reasoning_steps=[],
        prior_state=ChildState.MISCONCEPTION,
        new_state=ChildState.CAN_EXPLAIN,
        affect="explaining",
        explanation_hint_hi="",
        numbers_involved=[2, 7, 45],
    )
    # Valid line with permitted numbers
    valid, _ = validate_child_voice("2 mein se 7 nahi hota, 45!", rule_res, correct_answer=35)
    assert valid is True

    # Unauthorized number (e.g. mentions 99 out of nowhere)
    invalid, reason = validate_child_voice("Mera uttar 99 hai", rule_res, correct_answer=35)
    assert invalid is False
    assert "99" in reason

    # Leaked correct answer while in misconception state
    leaked, leak_reason = validate_child_voice("Uttar 35 hai", rule_res, correct_answer=35)
    assert leaked is False
    assert "Leaked correct answer" in leak_reason


def test_validate_coach_feedback_quotes():
    transcript = "Ravi, 52 mein se 17 kaise ghataya? Batao."
    feedback = CoachFeedbackOutput(
        scores={"c1": 1},
        evidence={"c1": "Ravi, 52 mein se 17 kaise ghataya?"},
        strength_hi="Aapne bachhe se uska tarika pucha.",
        change_hi="Agli baar bundle aur teeli se dikhayein.",
        exact_words_hi="5 bundle aur 2 teeli lekar dekho.",
        confidence=0.85,
    )
    valid, _ = validate_coach_feedback(feedback, transcript)
    assert valid is True

    # Non-existent quote
    bad_feedback = CoachFeedbackOutput(
        scores={"c1": 1},
        evidence={"c1": "Yeh baat transcript mein bilkul nahi hai"},
        strength_hi="Achha kiya.",
        change_hi="Badlo.",
        exact_words_hi="Yeh bolo.",
        confidence=0.85,
    )
    invalid, reason = validate_coach_feedback(bad_feedback, transcript)
    assert invalid is False
    assert "not found in transcript" in reason
