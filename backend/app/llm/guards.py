"""Guard functions to validate Claude outputs before sending to users (§5.1, §5.3, §5.5, §5.10, §6, §8, §9)."""

import re
import unicodedata
from typing import Any

import rapidfuzz

from backend.app.config import settings
from backend.app.llm.hindi_numbers import DEVANAGARI_DIGITS, extract_numbers
from backend.app.llm.schemas import (
    CoachFeedbackOutput,
    FidelityCheckerOutput,
    GuideAnswererOutput,
)
from backend.app.rule_engine.child_state import ChildState
from backend.app.rule_engine.domain import ChildResponse, ResponseKind


def norm(s: str) -> str:
    """Canonical text normalisation for guards (spec/05 §5.10).

    NFC → lowercase Latin → Devanagari digits → Arabic → strip punctuation
    `।,.!?;:"'()-–—` → collapse whitespace → remove nukta variants → remove zero-width joiners.
    """
    if not s:
        return ""
    # 1. NFC
    s = unicodedata.normalize("NFC", s)
    # 2. Lowercase Latin
    s = s.lower()
    # 3. Devanagari digits -> Arabic
    for i, d in enumerate(DEVANAGARI_DIGITS):
        s = s.replace(d, str(i))
    # 4. Remove zero-width joiners
    s = s.replace("\u200c", "").replace("\u200d", "")
    # 5. Nukta canonicalisation via NFC
    s = unicodedata.normalize("NFC", s)
    # 6. Strip punctuation: ।,!?;:"'()-–—`'’‘“” and period
    s = re.sub(r"[।,!\?;:\"\'\(\)\-–—`’‘“”\.]", " ", s)
    # 7. Collapse whitespace
    s = re.sub(r"\s+", " ", s).strip()
    return s


def substring_match(quote: str, source: str, min_fuzzy: float = 90.0) -> bool:
    """Verifies that normalized quote is present in normalized source, or satisfies fuzzy ratio."""
    norm_q = norm(quote)
    norm_s = norm(source)
    if not norm_q:
        return True
    if norm_q in norm_s:
        return True
    ratio = rapidfuzz.fuzz.partial_ratio(norm_q, norm_s)
    return float(ratio) >= min_fuzzy


def normalize_hindi_text(text: str) -> str:
    """NFC normalization for Hindi and Devanagari text (§18)."""
    return unicodedata.normalize("NFC", text.strip())


def extract_numbers_from_text(text: str) -> list[int]:
    """Extracts integers from text (Arabic digits, Devanagari numerals, Hindi words)."""
    return extract_numbers(text)


def guard_child_line(
    line_hi: str,
    response: ChildResponse,
) -> tuple[bool, str]:
    """Guard for child voice lines matching spec/05 §5.5."""
    # 1. SILENT kind must be empty string
    if response.kind == ResponseKind.SILENT:
        if line_hi.strip():
            return False, "Silent child must produce empty line"
        return True, "Valid"

    # 1b. Length check: 1 to MAX_CHILD_LINE_WORDS
    words = line_hi.strip().split()
    if not words:
        return False, "Child line cannot be empty"
    if len(words) > settings.MAX_CHILD_LINE_WORDS:
        return (
            False,
            f"Line exceeds max word count ({len(words)} > {settings.MAX_CHILD_LINE_WORDS})",
        )

    # 5. Stays in character
    disallowed_terms = ["ai", "assistant", "गलती", "misconception", "rule", "नियम"]
    line_lower = line_hi.lower()
    for term in disallowed_terms:
        if term in line_lower:
            return False, f"Line contains out-of-character term '{term}'"

    # Reject excessive English words (> 3 words)
    eng_tokens = re.findall(r"\b[a-zA-Z]+\b", line_hi)
    if len(eng_tokens) > 3:
        return False, "Line contains more than 3 English words"

    # 6. OFF_TOPIC / INTERJECT: contains no numbers at all
    extracted_nums = extract_numbers(line_hi)
    if response.kind in (ResponseKind.OFF_TOPIC, ResponseKind.INTERJECT):
        if extracted_nums:
            return False, f"Off-topic/interject response must not contain numbers: {extracted_nums}"
        return True, "Valid"

    # 2. Numbers: every extracted number must be in allowed_numbers
    for num in extracted_nums:
        if num not in response.allowed_numbers:
            return False, f"Number {num} not in allowed_numbers {response.allowed_numbers}"

    # For answer kinds, the answer must appear
    if response.kind in (
        ResponseKind.ANSWER,
        ResponseKind.EXPLAIN_BUG,
        ResponseKind.RELAPSE,
        ResponseKind.SCAFFOLDED_CORRECT,
        ResponseKind.CORRECT_EXPLAINED,
        ResponseKind.PARROT,
    ):
        if isinstance(response.answer, int):
            if response.answer not in extracted_nums:
                return False, f"Answer {response.answer} does not appear in line"
        elif isinstance(response.answer, str) and response.answer:
            ans_clean = norm(response.answer).replace(" ", "")
            line_clean = norm(line_hi).replace(" ", "")
            if ans_clean not in line_clean:
                return False, f"Literacy answer '{response.answer}' does not appear in line"

    # 3. Forbidden: no token in forbidden appears
    for forb in response.forbidden:
        if not forb:
            continue
        if forb.isdigit():
            forb_int = int(forb)
            if forb_int in extracted_nums:
                return False, f"Forbidden number {forb_int} appeared in line"
        forb_norm = norm(forb)
        if forb_norm and forb_norm in norm(line_hi):
            return False, f"Forbidden token '{forb}' appeared in line"

    return True, "Valid"


def validate_child_voice(
    line_hi: str,
    rule_result: Any,
    correct_answer: Any,
) -> tuple[bool, str]:
    """Legacy helper for child voice lines."""
    line_norm = normalize_hindi_text(line_hi)
    words = line_norm.split()

    if len(words) > settings.MAX_CHILD_LINE_WORDS:
        return (
            False,
            f"Line exceeds max word count ({len(words)} > {settings.MAX_CHILD_LINE_WORDS})",
        )

    extracted_nums = extract_numbers_from_text(line_norm)

    if rule_result.new_state in (ChildState.MISCONCEPTION, ChildState.CAN_EXPLAIN):
        if (
            isinstance(correct_answer, int)
            and correct_answer in extracted_nums
            and not rule_result.is_parrot
        ):
            return False, f"Leaked correct answer {correct_answer} during error state"

    allowed_nums = {
        int(n)
        for n in rule_result.numbers_involved
        if isinstance(n, (int, str)) and str(n).isdigit()
    }
    for num in extracted_nums:
        if num not in allowed_nums:
            return False, f"Number {num} not authorized by rule engine result {allowed_nums}"

    return True, "Valid"


def validate_coach_feedback(
    feedback: CoachFeedbackOutput,
    transcript: str,
) -> tuple[bool, str]:
    """Guard for coach rubric feedback (§5.3)."""
    for crit_id, quote in feedback.evidence.items():
        if quote and not substring_match(quote, transcript):
            return False, f"Evidence quote for {crit_id} not found in transcript: '{quote}'"

    total_spoken_words = len(
        f"{feedback.strength_hi} {feedback.change_hi} {feedback.exact_words_hi}".split()
    )
    if total_spoken_words > settings.MAX_COACH_FEEDBACK_WORDS:
        return (
            False,
            f"Feedback exceeds maximum word budget ({total_spoken_words} > {settings.MAX_COACH_FEEDBACK_WORDS})",
        )

    return True, "Valid"


def validate_fidelity_check(
    result: FidelityCheckerOutput,
    explanation_transcript: str,
) -> tuple[bool, str]:
    """Guard for 'explain it back' fidelity check (§6)."""
    for point in result.points:
        if point.status in ("covered", "partial"):
            if not point.quote:
                return False, f"Key point {point.id} marked {point.status} without supporting quote"
            if not substring_match(point.quote, explanation_transcript):
                return False, f"Quote for point {point.id} not in transcript: '{point.quote}'"

    return True, "Valid"


def validate_guide_answer(
    result: GuideAnswererOutput,
    retrieved_source_ids: list[str],
) -> tuple[bool, str]:
    """Guard for guide answers (§8)."""
    valid_sources = set(retrieved_source_ids)
    cited_sources = set(result.source_ids)

    if not cited_sources:
        return False, "Answer did not cite any source"

    if not cited_sources.issubset(valid_sources):
        return False, f"Cited sources {cited_sources} not in retrieved set {valid_sources}"

    words = normalize_hindi_text(result.answer_hi).split()
    if len(words) > settings.MAX_GUIDE_ANSWER_WORDS:
        return (
            False,
            f"Answer exceeds word budget ({len(words)} > {settings.MAX_GUIDE_ANSWER_WORDS})",
        )

    return True, "Valid"
