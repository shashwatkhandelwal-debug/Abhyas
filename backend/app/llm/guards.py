"""Guard functions to validate Claude outputs before sending to users.

Strictly follows AGENTS.md, spec/05 §5.3–§5.10, and T09 acceptance criteria:
- Every runtime and build-time Claude output is validated by pure guard functions.
- Normalized substring checks with fuzzy fallback (QUOTE_FUZZY_MIN).
- Number extraction and verification via hindi_numbers.py.
- Respectful register enforcement (आप / आपने, no तुम / तुमने with teachers).
"""

import re
import unicodedata

import rapidfuzz

from backend.app.config import settings
from backend.app.llm.hindi_numbers import DEVANAGARI_DIGITS, extract_numbers
from backend.app.llm.schemas import (
    ActTaggerOutput,
    CoachFeedbackOutput,
    FidelityCheckerOutput,
    GuideAnswererOutput,
    IntentRouterOutput,
    PageOCROutput,
    QuestionClassifierOutput,
    RetrievedChunk,
)
from backend.app.rule_engine.domain import (
    ChildResponse,
    ResponseKind,
    TeachingAct,
)

VALID_INTENTS: frozenset[str] = frozenset(
    {
        "answer_for_step",
        "question",
        "command_next",
        "command_skip",
        "command_repeat",
        "command_help",
        "smalltalk",
        "unclear",
    }
)

DISRESPECTFUL_WORDS: frozenset[str] = frozenset(
    {"तुम", "तुमने", "तुम्हारा", "तुम्हारे", "तुम्हारी", "तुमसे", "तुझे", "तेरा", "तेरी", "तेरे"}
)
RESPECTFUL_WORDS: frozenset[str] = frozenset({"आप", "आपने", "आपका", "आपके", "आपकी", "आपसे", "आपको"})


# ── Text Normalization & Substring Match (§5.10) ─────────────────────────────
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
    """NFC normalization for Hindi and Devanagari text."""
    return unicodedata.normalize("NFC", text.strip())


def extract_numbers_from_text(text: str) -> list[int]:
    """Extracts integers from text (Arabic digits, Devanagari numerals, Hindi words)."""
    return extract_numbers(text)


# ── 1. guard_intent_router (§5.3) ────────────────────────────────────────────
def guard_intent_router(output: IntentRouterOutput) -> tuple[bool, str]:
    """Validate intent_router output schema and bounds (§5.3)."""
    if output.intent not in VALID_INTENTS:
        return False, f"Invalid intent: {output.intent}"
    if not (0.0 <= output.confidence <= 1.0):
        return False, f"Confidence out of bounds: {output.confidence}"
    return True, "Valid"


# ── 2. guard_act_tagger (§5.4) ───────────────────────────────────────────────
def guard_act_tagger(
    output: ActTaggerOutput,
    transcript: str,
    scene_persona_ids: list[str],
) -> tuple[bool, str]:
    """Validate act_tagger output (§5.4).

    Guards:
    - every act in taxonomy (TeachingAct)
    - 1 to 4 acts maximum
    - addressed_child in scene persona ids | "all" | None
    - quote is a normalised substring of transcript or empty
    - if problem present, its numbers or word appear in transcript
    """
    if not output.acts:
        return False, "At least one act must be tagged"
    if len(output.acts) > 4:
        return False, f"Exceeds maximum of 4 acts ({len(output.acts)} > 4)"
    for act in output.acts:
        if act not in TeachingAct:
            return False, f"Invalid teaching act: {act}"

    allowed_addressed: set[str | None] = {*scene_persona_ids, "all", None}
    if output.addressed_child not in allowed_addressed:
        return False, f"Invalid addressed_child '{output.addressed_child}'"

    if output.quote.strip():
        if not substring_match(output.quote, transcript, min_fuzzy=settings.QUOTE_FUZZY_MIN):
            return False, f"quote not in transcript: '{output.quote}'"

    if output.problem is not None:
        p = output.problem
        transcript_numbers = set(extract_numbers(transcript))
        if p.a is not None and p.a not in transcript_numbers:
            return False, f"problem number a={p.a} absent from transcript"
        if p.b is not None and p.b not in transcript_numbers:
            return False, f"problem number b={p.b} absent from transcript"
        if p.tens is not None and p.tens not in transcript_numbers:
            return False, f"problem tens={p.tens} absent from transcript"
        if p.ones is not None and p.ones not in transcript_numbers:
            return False, f"problem ones={p.ones} absent from transcript"
        if p.word and norm(p.word) not in norm(transcript):
            return False, f"problem word '{p.word}' absent from transcript"

    return True, "Valid"


# ── 3. guard_child_line (§5.5) ───────────────────────────────────────────────
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

    # 5. Stays in character: match whole words for Latin and Devanagari tokens
    latin_disallowed = re.compile(r"\b(?:ai|assistant|rule|misconception)\b", re.IGNORECASE)
    if match := latin_disallowed.search(line_hi):
        return False, f"Line contains out-of-character term '{match.group(0)}'"

    devanagari_disallowed = re.compile(r"(?<![\u0900-\u097F\w])(?:गलती|नियम)(?![\u0900-\u097F\w])")
    if match := devanagari_disallowed.search(line_hi):
        return False, f"Line contains out-of-character term '{match.group(0)}'"

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

    # 3. Forbidden: check BEFORE answer check (prevents false answer error when forbidden number used)
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

    # 4. For answer kinds, the answer must appear
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

    return True, "Valid"


# ── 4. guard_coach (§5.6) ────────────────────────────────────────────────────
def guard_coach(
    output: CoachFeedbackOutput,
    rubric_criterion_ids: list[str],
    teacher_lines: list[str],
    rubric_rewards_not_telling: bool,
    current_item_answer: int | str | None,
) -> tuple[bool, str]:
    """Validate coach rubric feedback (§5.6).

    Guards:
    - keys of scores == rubric_criterion_ids exactly
    - values of scores in {0, 1, 2}
    - for every score > 0, evidence is normalised substring of teacher line
    - strength, change, exact_words each single sentence (<= 1 period/danda inside)
    - total words across the three <= MAX_COACH_FEEDBACK_WORDS (60)
    - respectful register: coach uses आप/आपने and never तुम/तुमने with teacher
    - exact_words_hi must not contain correct answer if rubric rewards not telling
    - confidence in [0.0, 1.0]
    """
    if set(output.scores.keys()) != set(rubric_criterion_ids):
        return (
            False,
            f"Rubric criteria keys mismatch: expected {set(rubric_criterion_ids)}, got {set(output.scores.keys())}",
        )

    for crit_id, score in output.scores.items():
        if score not in (0, 1, 2):
            return False, f"Score for {crit_id} must be in {{0, 1, 2}}, got {score}"

    for crit_id, score in output.scores.items():
        if score > 0:
            quote = output.evidence.get(crit_id, "").strip()
            if not quote:
                return False, f"Evidence quote missing for criterion {crit_id} with score {score}"
            if not any(
                substring_match(quote, line, min_fuzzy=settings.QUOTE_FUZZY_MIN)
                for line in teacher_lines
            ):
                return (
                    False,
                    f"Evidence quote for {crit_id} not in teacher transcript: '{quote}'",
                )

    # Word budget
    total_words = (
        len(output.strength_hi.split())
        + len(output.change_hi.split())
        + len(output.exact_words_hi.split())
    )
    if total_words > settings.MAX_COACH_FEEDBACK_WORDS:
        return (
            False,
            f"Coach feedback exceeds word budget ({total_words} > {settings.MAX_COACH_FEEDBACK_WORDS})",
        )

    # Single sentence checks
    for field_name, sentence in [
        ("strength_hi", output.strength_hi),
        ("change_hi", output.change_hi),
        ("exact_words_hi", output.exact_words_hi),
    ]:
        stripped = sentence.strip().rstrip("।,.!? ")
        inner_terminators = len(re.findall(r"[।\.]", stripped))
        if inner_terminators > 1:
            return (
                False,
                f"{field_name} must be a single sentence (found {inner_terminators} internal stops)",
            )

    # Respectful register: coach addressing the teacher in strength_hi and change_hi
    coach_evaluation = f"{output.strength_hi} {output.change_hi}"
    coach_tokens = set(norm(coach_evaluation).split())
    if coach_tokens & DISRESPECTFUL_WORDS:
        return False, "Disrespectful register: coach must not use तुम/तुमने with teacher"
    if not (coach_tokens & RESPECTFUL_WORDS):
        return False, "Coach feedback must use respectful register (आप/आपने)"

    # Answer leak prevention in exact_words_hi
    if rubric_rewards_not_telling and current_item_answer is not None:
        if isinstance(current_item_answer, int):
            exact_numbers = extract_numbers(output.exact_words_hi)
            if current_item_answer in exact_numbers:
                return (
                    False,
                    f"Coach leaked correct answer {current_item_answer} in exact_words_hi",
                )
        elif isinstance(current_item_answer, str) and current_item_answer.strip():
            if norm(current_item_answer) in norm(output.exact_words_hi):
                return (
                    False,
                    f"Coach leaked correct answer '{current_item_answer}' in exact_words_hi",
                )

    if not (0.0 <= output.confidence <= 1.0):
        return False, f"Confidence out of bounds: {output.confidence}"

    return True, "Valid"


# ── 5. guard_fidelity_checker (§5.7) ─────────────────────────────────────────
def guard_fidelity_checker(
    output: FidelityCheckerOutput,
    *,
    expected_point_ids: list[str],
    transcript: str,
) -> tuple[bool, str]:
    """Validate fidelity_checker explain-it-back output (§5.7).

    Guards:
    - one entry per key point id, no extras, no duplicates
    - covered | partial require quote that is normalised substring of transcript
    - missing requires empty quote
    - misconceptions <= 3, each <= 25 words
    - confidence in [0.0, 1.0]
    """
    point_ids = [p.id for p in output.points]
    if len(point_ids) != len(set(point_ids)):
        return False, f"Duplicate key point IDs in output: {point_ids}"

    if len(point_ids) != len(expected_point_ids) or set(point_ids) != set(expected_point_ids):
        return (
            False,
            f"Evaluated key points do not match expected IDs: expected {set(expected_point_ids)}, got {set(point_ids)}",
        )

    for p in output.points:
        if p.status in ("covered", "partial"):
            if not p.quote.strip():
                return False, f"Key point {p.id} marked {p.status} without supporting quote"
            if not substring_match(p.quote, transcript, min_fuzzy=settings.QUOTE_FUZZY_MIN):
                return False, f"quote for point {p.id} not found in transcript: '{p.quote}'"
        elif p.status == "missing":
            if p.quote.strip():
                return False, f"Key point {p.id} marked missing but contains quote: '{p.quote}'"

    if len(output.misconceptions) > 3:
        return False, f"Too many misconceptions ({len(output.misconceptions)} > 3)"

    for m in output.misconceptions:
        if len(m.split()) > 25:
            return False, f"Misconception exceeds 25 words: '{m}'"

    if not (0.0 <= output.confidence <= 1.0):
        return False, f"Confidence out of bounds: {output.confidence}"

    return True, "Valid"


# ── 6. guard_question_classifier (§5.8) ──────────────────────────────────────
def guard_question_classifier(output: QuestionClassifierOutput) -> tuple[bool, str]:
    """Validate question_classifier output (§5.8).

    Guards:
    - category in (pedagogy, classroom_management, admin, out_of_scope)
    - confidence in [0.0, 1.0]
    - if needs_clarification: clarifying_question_hi non-empty and <= 20 words
    - if pedagogy/classroom_management without clarification: search_query_hi non-empty
    """
    if output.category not in ("pedagogy", "classroom_management", "admin", "out_of_scope"):
        return False, f"Invalid category: {output.category}"

    if not (0.0 <= output.confidence <= 1.0):
        return False, f"Confidence out of bounds: {output.confidence}"

    if output.needs_clarification:
        if not output.clarifying_question_hi.strip():
            return False, "clarifying_question_hi cannot be empty when clarification is needed"
        words = output.clarifying_question_hi.split()
        if len(words) > 20:
            return False, f"clarifying_question exceeds 20 words ({len(words)} > 20)"
        clar_tokens = set(norm(output.clarifying_question_hi).split())
        if clar_tokens & DISRESPECTFUL_WORDS:
            return False, "Disrespectful register: clarifying question must not use तुम/तुमने"

    if output.category in ("pedagogy", "classroom_management") and not output.needs_clarification:
        if not output.search_query_hi.strip():
            return (
                False,
                "search_query_hi must not be empty for pedagogy or classroom_management",
            )

    return True, "Valid"


# ── 7. guard_guide_answerer (§5.8) ───────────────────────────────────────────
def guard_guide_answerer(
    output: GuideAnswererOutput,
    *,
    retrieved_chunks: list[RetrievedChunk],
) -> tuple[bool, str]:
    """Validate guide_answerer output (§5.8).

    Guards:
    - source_ids non-empty and subset of retrieved_chunks
    - answer <= MAX_GUIDE_ANSWER_WORDS (80)
    - every number in answer appears in cited chunks text
    - respectful register (no तुम/तुमने)
    - try_this_week_hi <= 20 words and respectful register
    - confidence in [0.0, 1.0]
    """
    if not output.source_ids:
        return False, "Guide answer must cite at least one source ID"

    retrieved_set = {c.chunk_id for c in retrieved_chunks}
    if not set(output.source_ids).issubset(retrieved_set):
        return (
            False,
            f"Cited source IDs {output.source_ids} not in retrieved sources {retrieved_set}",
        )

    words = output.answer_hi.split()
    if len(words) > settings.MAX_GUIDE_ANSWER_WORDS:
        return (
            False,
            f"Answer exceeds maximum word budget ({len(words)} > {settings.MAX_GUIDE_ANSWER_WORDS})",
        )

    ans_tokens = set(norm(output.answer_hi).split())
    if ans_tokens & DISRESPECTFUL_WORDS:
        return False, "Disrespectful register: guide answer must not use तुम/तुमने"

    if output.try_this_week_hi:
        tip_words = output.try_this_week_hi.split()
        if len(tip_words) > 20:
            return False, f"try_this_week exceeds 20 words ({len(tip_words)} > 20)"
        tip_tokens = set(norm(output.try_this_week_hi).split())
        if tip_tokens & DISRESPECTFUL_WORDS:
            return False, "Disrespectful register: try_this_week must not use तुम/तुमने"

    # Number integrity against cited chunks text
    cited_chunks = [c for c in retrieved_chunks if c.chunk_id in output.source_ids]
    cited_text = " ".join(c.text for c in cited_chunks)
    cited_numbers = set(extract_numbers(cited_text))
    answer_numbers = extract_numbers(output.answer_hi)
    for num in answer_numbers:
        if num not in cited_numbers:
            return False, f"Unauthorized number {num} in guide answer"

    if not (0.0 <= output.confidence <= 1.0):
        return False, f"Confidence out of bounds: {output.confidence}"

    return True, "Valid"


# ── 8. guard_page_ocr (§5.9) ─────────────────────────────────────────────────
def guard_page_ocr(output: PageOCROutput) -> tuple[bool, str]:
    """Validate page_ocr output (§5.9).

    Guard:
    - Devanagari character ratio >= 0.60
    """
    non_space_chars = [c for c in output.text_hi if not c.isspace()]
    if not non_space_chars:
        return False, "Devanagari OCR text is empty"

    devanagari_chars = [c for c in non_space_chars if "\u0900" <= c <= "\u097f"]
    ratio = len(devanagari_chars) / len(non_space_chars)
    if ratio < 0.60:
        return False, f"Devanagari character ratio too low ({ratio:.2f} < 0.60)"

    return True, "Valid"
