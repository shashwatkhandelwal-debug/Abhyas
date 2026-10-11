"""Guard functions to validate Claude outputs before sending to users (§5.1, §5.3, §6, §8, §9)."""

import re
import unicodedata
from typing import Any
from backend.app.config import settings
from backend.app.llm.schemas import (
    ActTaggerOutput,
    CoachFeedbackOutput,
    FidelityCheckerOutput,
    GuideAnswererOutput,
)
from backend.app.rule_engine.child_state import ChildState
from backend.app.rule_engine.engine import RuleEngineResult


def normalize_hindi_text(text: str) -> str:
    """NFC normalization for Hindi and Devanagari text (§18)."""
    return unicodedata.normalize("NFC", text.strip())


def extract_numbers_from_text(text: str) -> list[int]:
    """Extracts Arabic and Devanagari numeral integers from text."""
    # Convert Devanagari digits to standard digits
    devanagari_digits = "०१२३४५६७८९"
    mapped = text
    for i, d in enumerate(devanagari_digits):
        mapped = mapped.replace(d, str(i))
    
    # Extract integer matches
    matches = re.findall(r"\b\d+\b", mapped)
    return [int(m) for m in matches]


def validate_child_voice(
    line_hi: str,
    rule_result: RuleEngineResult,
    correct_answer: Any,
) -> tuple[bool, str]:
    """Guard for child voice lines (§5.1, §9).
    
    Returns (is_valid, reason).
    """
    line_norm = normalize_hindi_text(line_hi)
    words = line_norm.split()
    
    # 1. Word length check
    if len(words) > settings.MAX_CHILD_LINE_WORDS:
        return False, f"Line exceeds max word count ({len(words)} > {settings.MAX_CHILD_LINE_WORDS})"

    extracted_nums = extract_numbers_from_text(line_norm)

    # 2. Leaked correct answer check if still in error state
    if rule_result.new_state in (ChildState.MISCONCEPTION, ChildState.CAN_EXPLAIN):
        if isinstance(correct_answer, int) and correct_answer in extracted_nums and not rule_result.is_parrot:
            return False, f"Leaked correct answer {correct_answer} during error state"

    # 3. Authorized numbers check
    allowed_nums = set(int(n) for n in rule_result.numbers_involved if isinstance(n, (int, str)) and str(n).isdigit())
    for num in extracted_nums:
        if num not in allowed_nums:
            return False, f"Number {num} not authorized by rule engine result {allowed_nums}"

    return True, "Valid"


def validate_coach_feedback(
    feedback: CoachFeedbackOutput,
    transcript: str,
) -> tuple[bool, str]:
    """Guard for coach rubric feedback (§5.3)."""
    norm_transcript = normalize_hindi_text(transcript).lower()
    
    # Verify evidence quotes exist in the transcript
    for crit_id, quote in feedback.evidence.items():
        if quote and normalize_hindi_text(quote).lower() not in norm_transcript:
            return False, f"Evidence quote for {crit_id} not found in transcript: '{quote}'"

    # Spoken word count check
    total_spoken_words = len(
        f"{feedback.strength_hi} {feedback.change_hi} {feedback.exact_words_hi}".split()
    )
    if total_spoken_words > settings.MAX_COACH_FEEDBACK_WORDS:
        return False, f"Feedback exceeds maximum word budget ({total_spoken_words} > {settings.MAX_COACH_FEEDBACK_WORDS})"

    return True, "Valid"


def validate_fidelity_check(
    result: FidelityCheckerOutput,
    explanation_transcript: str,
) -> tuple[bool, str]:
    """Guard for 'explain it back' fidelity check (§6)."""
    norm_transcript = normalize_hindi_text(explanation_transcript).lower()
    
    for point in result.points:
        if point.status in ("covered", "partial"):
            if not point.quote:
                return False, f"Key point {point.id} marked {point.status} without supporting quote"
            if normalize_hindi_text(point.quote).lower() not in norm_transcript:
                return False, f"Quote for point {point.id} not in transcript: '{point.quote}'"

    return True, "Valid"


def validate_guide_answer(
    result: GuideAnswererOutput,
    retrieved_source_ids: list[str],
) -> tuple[bool, str]:
    """Guard for guide answers (§8)."""
    # 1. At least one source must be from retrieved set
    valid_sources = set(retrieved_source_ids)
    cited_sources = set(result.source_ids)
    
    if not cited_sources:
        return False, "Answer did not cite any source"
    
    if not cited_sources.issubset(valid_sources):
        return False, f"Cited sources {cited_sources} not in retrieved set {valid_sources}"

    # 2. Length check
    words = normalize_hindi_text(result.answer_hi).split()
    if len(words) > settings.MAX_GUIDE_ANSWER_WORDS:
        return False, f"Answer exceeds word budget ({len(words)} > {settings.MAX_GUIDE_ANSWER_WORDS})"

    return True, "Valid"
