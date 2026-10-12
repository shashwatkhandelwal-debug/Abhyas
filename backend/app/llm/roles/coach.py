"""Coach role implementation matching spec/05 §5.6.

Evaluates teacher rehearsal scenes against move rubrics using Claude smart model
(or MockLLM) with deterministic scoring and feedback bank fallback.
"""

import logging
import re
import unicodedata
from typing import Any

from backend.app.config import settings
from backend.app.content_models import FeedbackItem, MoveCard, Rubric
from backend.app.db.models import ReviewItem
from backend.app.llm.client import LLMUnavailable, call_tool
from backend.app.llm.guards import guard_coach, norm
from backend.app.llm.hindi_numbers import extract_numbers
from backend.app.llm.prompts import load_prompt
from backend.app.llm.roles.act_tagger import FALLBACK_PATTERNS
from backend.app.llm.schemas import CoachFeedbackOutput

logger = logging.getLogger("abhyas.llm.coach")

PROMPT_VERSION = "v1"


def _to_transcript_str(transcript: str | list[str] | list[dict[str, Any]]) -> str:
    """Converts transcript into a uniform multi-line string."""
    if isinstance(transcript, str):
        return unicodedata.normalize("NFC", transcript)
    if isinstance(transcript, list):
        lines: list[str] = []
        for item in transcript:
            if isinstance(item, str):
                lines.append(item.strip())
            elif isinstance(item, dict):
                speaker = item.get("speaker", "teacher")
                text = item.get("text_hi", item.get("text", ""))
                lines.append(f"{speaker}: {text}".strip())
        return unicodedata.normalize("NFC", "\n".join(lines))
    return unicodedata.normalize("NFC", str(transcript))


def _extract_teacher_turns(transcript: str) -> list[str]:
    """Extracts pure teacher turns from dialogue transcript."""
    turns: list[str] = []
    for raw_line in transcript.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        line_lower = line.lower()
        if "teacher:" in line_lower or "टीचर:" in line or "टीचर :" in line:
            parts = re.split(r"(?:teacher|टीचर)\s*[:：]", line, flags=re.IGNORECASE)
            if len(parts) > 1 and parts[1].strip():
                turns.append(parts[1].strip())
        elif ":" in line and any(
            role in line_lower
            for role in [
                "ravi",
                "priya",
                "aman",
                "रवि",
                "प्रिया",
                "अमन",
                "child",
                "बच्चा",
            ]
        ):
            continue
        else:
            turns.append(line)
    return turns


def _parse_act_tags(
    act_tags: Any,
    teacher_turns: list[str],
) -> tuple[list[list[str]], set[str]]:
    """Parses act tags into per-turn lists and a global set of occurring acts."""
    all_acts: set[str] = set()
    acts_by_turn: list[list[str]] = [[] for _ in teacher_turns]

    def _normalize_act(a: Any) -> str:
        if hasattr(a, "value"):
            return str(a.value).strip().lower()
        return str(a).strip().lower()

    if isinstance(act_tags, list):
        if act_tags and isinstance(act_tags[0], list):
            for i, turn_acts in enumerate(act_tags):
                parsed_turn = [_normalize_act(a) for a in turn_acts]
                if i < len(acts_by_turn):
                    acts_by_turn[i] = parsed_turn
                for a in parsed_turn:
                    all_acts.add(a)
        else:
            flat = [_normalize_act(a) for a in act_tags]
            for a in flat:
                all_acts.add(a)
            if len(flat) == len(teacher_turns):
                for i, a in enumerate(flat):
                    acts_by_turn[i] = [a]
    elif isinstance(act_tags, dict):
        for k, v in act_tags.items():
            parsed_turn = [_normalize_act(a) for a in (v if isinstance(v, list) else [v])]
            if isinstance(k, int) and 0 <= k < len(acts_by_turn):
                acts_by_turn[k] = parsed_turn
            for a in parsed_turn:
                all_acts.add(a)

    return acts_by_turn, all_acts


def _check_child_advanced(child_trajectories: Any) -> bool:
    """Checks whether any simulated child advanced understanding."""
    if not child_trajectories:
        return False
    if isinstance(child_trajectories, bool):
        return child_trajectories
    if isinstance(child_trajectories, dict):
        for v in child_trajectories.values():
            if isinstance(v, bool) and v:
                return True
            if isinstance(v, (list, tuple)) and len(v) >= 2:
                first, last = v[0], v[-1]
                if isinstance(first, (int, float)) and isinstance(last, (int, float)):
                    if last > first:
                        return True
                if hasattr(first, "value") and hasattr(last, "value"):
                    if str(last) != str(first):
                        return True
            if isinstance(v, dict):
                start = v.get("start") or v.get("start_state")
                end = v.get("end") or v.get("end_state")
                if (
                    isinstance(start, (int, float))
                    and isinstance(end, (int, float))
                    and end > start
                ):
                    return True
                if start and end and start != end:
                    return True
    elif isinstance(child_trajectories, (list, tuple)):
        for item in child_trajectories:
            if isinstance(item, bool) and item:
                return True
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                if isinstance(item[0], (int, float)) and isinstance(item[-1], (int, float)):
                    if item[-1] > item[0]:
                        return True
            if hasattr(item, "advanced") and bool(item.advanced):
                return True
            if hasattr(item, "start_state") and hasattr(item, "end_state"):
                if item.end_state > item.start_state:
                    return True
    return False


def _is_rubric_rewarding_not_telling(move: MoveCard) -> bool:
    """Determines whether the move rubric penalises telling the answer."""
    for crit in move.rubric.criteria:
        neg_acts = [a.lower() for a in crit.negative_acts]
        if "tell_answer" in neg_acts:
            return True
        if "no_telling" in crit.id.lower():
            return True
    return False


def _extract_item_answer(move: MoveCard) -> int | str | None:
    """Extracts target item answer from move scenario items if present."""
    if not move.scenario or not move.scenario.items:
        return None
    item = move.scenario.items[0]
    item_type = item.get("type", "")
    if item_type == "sub":
        a = item.get("a")
        b = item.get("b")
        if a is not None and b is not None:
            return int(a) - int(b)
    elif item_type == "add":
        a = item.get("a")
        b = item.get("b")
        if a is not None and b is not None:
            return int(a) + int(b)
    elif item_type == "place_value":
        tens = item.get("tens", 0)
        ones = item.get("ones", 0)
        return int(tens) * 10 + int(ones)
    elif item_type == "read_word":
        word = item.get("word")
        return str(word) if word else None
    return None


def _sanitize_exact_words(
    exact_words_hi: str,
    current_item_answer: int | str | None,
    rubric_rewards_not_telling: bool,
    domain_str: str = "math",
) -> str:
    """Prevents answer leak in exact_words_hi if rubric rewards not telling."""
    if not rubric_rewards_not_telling or current_item_answer is None:
        return unicodedata.normalize("NFC", exact_words_hi)

    leaks = False
    if isinstance(current_item_answer, int):
        extracted_numbers = extract_numbers(exact_words_hi)
        if current_item_answer in extracted_numbers:
            leaks = True
    elif isinstance(current_item_answer, str) and current_item_answer.strip():
        if norm(current_item_answer) in norm(exact_words_hi):
            leaks = True

    if leaks:
        if domain_str == "literacy" or isinstance(current_item_answer, str):
            sanitized = "दोनों बच्चों के उत्तर स्लेट पर लिखकर पूछिए: कौन-सा शब्द सही है?"
        else:
            sanitized = "दोनों उत्तर स्लेट पर रखकर पूछिए: तीलियाँ गिनकर बताओ, कौन-सा तरीका सही है?"
        return unicodedata.normalize("NFC", sanitized)

    return unicodedata.normalize("NFC", exact_words_hi)


def _find_quote_for_signal_acts(
    signal_acts: list[str],
    teacher_turns: list[str],
    acts_by_turn: list[list[str]],
) -> str:
    """Finds an exact teacher quote demonstrating one of the signal acts."""
    signal_set = {s.strip().lower() for s in signal_acts}
    # 1. Turn tagged with a signal act
    for i, acts in enumerate(acts_by_turn):
        if any(a in signal_set for a in acts):
            if i < len(teacher_turns) and teacher_turns[i].strip():
                return teacher_turns[i].strip()

    # 2. Keyword fallback pattern matching
    for turn_text in teacher_turns:
        for pattern, act_enum in FALLBACK_PATTERNS:
            if act_enum.value.lower() in signal_set and pattern.search(turn_text):
                return turn_text.strip()

    # 3. Default to first non-empty teacher line
    for turn_text in teacher_turns:
        if turn_text.strip():
            return turn_text.strip()

    return ""


def _format_key_points(move: MoveCard) -> str:
    """Formats key points for the coach prompt."""
    if not move.key_points:
        return "कोई मुख्य बिंदु नहीं"
    return "\n".join(f"- {kp.id}: {kp.text_hi}" for kp in move.key_points)


def _format_rubric(rubric: Rubric) -> str:
    """Formats rubric criteria with level descriptors for the coach prompt."""
    lines: list[str] = []
    for c in rubric.criteria:
        lines.append(f"- Criterion '{c.id}': {c.text_hi}")
        lines.append(f"  Levels: {c.levels}")
        lines.append(f"  Signal acts: {c.signal_acts}")
        lines.append(f"  Negative acts: {c.negative_acts}")
    return "\n".join(lines)


def _format_feedback_bank(feedback_bank: dict[str, FeedbackItem]) -> str:
    """Formats feedback bank items for the coach prompt."""
    lines: list[str] = []
    for crit_id, item in feedback_bank.items():
        lines.append(f"- {crit_id}:")
        lines.append(f"  Strength: {item.strength_hi}")
        lines.append(f"  Change: {item.change_hi}")
        lines.append(f"  Exact words: {item.exact_words_hi}")
    return "\n".join(lines)


def _format_acts(act_tags: Any) -> str:
    """Formats detected acts per turn."""
    if not act_tags:
        return "कोई विशेष शिक्षण कार्य दर्ज नहीं"
    if isinstance(act_tags, list):
        lines: list[str] = []
        for i, turn in enumerate(act_tags):
            if isinstance(turn, list):
                acts_str = ", ".join(getattr(a, "value", str(a)) for a in turn)
            else:
                acts_str = getattr(turn, "value", str(turn))
            lines.append(f"Turn {i + 1}: [{acts_str}]")
        return "\n".join(lines)
    return str(act_tags)


def _format_trajectories(child_trajectories: Any) -> str:
    """Formats child trajectories for the coach prompt."""
    if not child_trajectories:
        return "बच्चों की समझ में बदलाव का कोई डेटा नहीं"
    if isinstance(child_trajectories, dict):
        lines: list[str] = []
        for child, traj in child_trajectories.items():
            lines.append(f"- {child}: {traj}")
        return "\n".join(lines)
    return str(child_trajectories)


def _format_retry(attempt: int, previous_change_hi: str | None) -> str:
    """Formats retry context for the coach prompt."""
    if attempt > 1 and previous_change_hi:
        return f'Last attempt you asked the teacher to change: "{previous_change_hi}". State whether she made this change.'
    return "First rehearsal attempt."


def create_coach_review_item(
    ref_id: str,
    confidence: float,
    reason: str | None = None,
    db: Any = None,
) -> ReviewItem:
    """Instantiates a ReviewItem for low confidence or fallback scoring."""
    item = ReviewItem(
        kind="rehearsal_score",
        ref_id=ref_id,
        reason=reason or f"Coach confidence {confidence:.2f} below threshold",
        status="open",
    )
    if db is not None:
        try:
            db.add(item)
        except Exception as exc:
            logger.warning("Could not persist review_item: %s", exc)
    return item


def fallback_coach_feedback(
    move: MoveCard,
    transcript: str | list[str] | list[dict[str, Any]],
    act_tags: Any = None,
    child_trajectories: Any = None,
    current_item_answer: int | str | None = None,
    attempt: int = 1,
    previous_change_hi: str | None = None,
) -> CoachFeedbackOutput:
    """Deterministic fallback coach feedback matching spec/05 §5.6.

    Scores each criterion from act tags:
    - 2 if a signal act occurred and target child advanced
    - 1 if occurred without advancement
    - 0 otherwise (or if negative act occurred)
    Strength, change, and exact_words are picked from move.feedback_bank.
    Sets confidence = 0.3, needs_review = True.
    """
    transcript_str = _to_transcript_str(transcript)
    teacher_turns = _extract_teacher_turns(transcript_str)
    acts_by_turn, all_acts = _parse_act_tags(act_tags, teacher_turns)

    # If act_tags was empty, infer acts from teacher turns using keyword patterns
    if not all_acts and teacher_turns:
        for i, turn_text in enumerate(teacher_turns):
            turn_detected: list[str] = []
            for pattern, act_enum in FALLBACK_PATTERNS:
                if pattern.search(turn_text):
                    act_str = act_enum.value.lower()
                    turn_detected.append(act_str)
                    all_acts.add(act_str)
            if turn_detected:
                acts_by_turn[i] = turn_detected

    child_advanced = _check_child_advanced(child_trajectories)

    if current_item_answer is None:
        current_item_answer = _extract_item_answer(move)

    rubric_rewards_not_telling = _is_rubric_rewarding_not_telling(move)

    scores: dict[str, int] = {}
    evidence: dict[str, str] = {}

    for crit in move.rubric.criteria:
        crit_id = crit.id
        crit_signal_acts = [a.lower() for a in crit.signal_acts]
        crit_negative_acts = [a.lower() for a in crit.negative_acts]

        # Negative acts force score 0
        has_negative = any(neg in all_acts for neg in crit_negative_acts)
        if has_negative:
            scores[crit_id] = 0
            evidence[crit_id] = ""
            continue

        # Signal acts determine score 2 or 1
        has_signal = any(sig in all_acts for sig in crit_signal_acts)
        if has_signal:
            quote = _find_quote_for_signal_acts(crit_signal_acts, teacher_turns, acts_by_turn)
            if quote:
                scores[crit_id] = 2 if child_advanced else 1
                evidence[crit_id] = quote
            else:
                scores[crit_id] = 0
                evidence[crit_id] = ""
        else:
            scores[crit_id] = 0
            evidence[crit_id] = ""

    # Select best and worst criteria for feedback items
    criteria = move.rubric.criteria
    best_crit = max(criteria, key=lambda c: scores.get(c.id, 0))

    min_score = min(scores.values()) if scores else 0
    worst_candidates = [c for c in criteria if scores.get(c.id, 0) == min_score]
    worst_crit = worst_candidates[0] if worst_candidates else criteria[-1]

    fb_best = move.feedback_bank.get(best_crit.id) or next(iter(move.feedback_bank.values()))
    fb_worst = move.feedback_bank.get(worst_crit.id) or next(iter(move.feedback_bank.values()))

    strength_hi = fb_best.strength_hi
    change_hi = fb_worst.change_hi

    domain_str = (
        "literacy" if getattr(move, "domain", None) == "literacy" or "LIT" in move.id else "math"
    )
    exact_words_hi = _sanitize_exact_words(
        fb_worst.exact_words_hi,
        current_item_answer,
        rubric_rewards_not_telling,
        domain_str=domain_str,
    )

    improved_since_last = False
    if attempt > 1 and previous_change_hi:
        improved_since_last = any(s > 0 for s in scores.values())

    output = CoachFeedbackOutput(
        scores=scores,
        evidence=evidence,
        strength_hi=unicodedata.normalize("NFC", strength_hi),
        change_hi=unicodedata.normalize("NFC", change_hi),
        exact_words_hi=unicodedata.normalize("NFC", exact_words_hi),
        improved_since_last=improved_since_last,
        confidence=0.3,
        needs_review=True,
    )
    return output


async def coach_feedback(
    move: MoveCard,
    transcript: str | list[str] | list[dict[str, Any]],
    act_tags: Any = None,
    child_trajectories: Any = None,
    attempt: int = 1,
    previous_change_hi: str | None = None,
    current_item_answer: int | str | None = None,
    ref_id: str = "scene",
    db: Any = None,
) -> CoachFeedbackOutput:
    """Generates coach feedback for a rehearsal scene matching spec/05 §5.6.

    Invokes Claude smart model with forced tool schema, validates with guard_coach,
    retries once on failure, and falls back to deterministic scoring.
    """
    transcript_str = _to_transcript_str(transcript)
    rubric_criterion_ids = [c.id for c in move.rubric.criteria]
    rubric_rewards_not_telling = _is_rubric_rewarding_not_telling(move)

    if current_item_answer is None:
        current_item_answer = _extract_item_answer(move)

    try:
        system_template = load_prompt("coach", PROMPT_VERSION)
    except FileNotFoundError:
        system_template = "You evaluate teacher rehearsal. Return coach_feedback tool call."

    system_prompt = system_template.format(
        move_title_hi=move.title_hi,
        effective_acts_hi=", ".join(move.teaching_acts_effective),
        key_points_block=_format_key_points(move),
        rubric_block=_format_rubric(move.rubric),
        feedback_bank_block=_format_feedback_bank(move.feedback_bank),
        transcript=transcript_str,
        acts_block=_format_acts(act_tags),
        trajectory_block=_format_trajectories(child_trajectories),
        retry_block=_format_retry(attempt, previous_change_hi),
    )

    messages: list[dict[str, Any]] = [
        {
            "role": "user",
            "content": f"Please evaluate this rehearsal transcript for move '{move.title_hi}'.",
        }
    ]

    for attempt_idx in range(2):
        try:
            tool_input = await call_tool(
                role="coach",
                model=settings.CLAUDE_MODEL_SMART,
                system=system_prompt,
                messages=messages,
                tool_name="coach_feedback",
                input_schema=CoachFeedbackOutput.model_json_schema(),
                temperature=0.2,
                max_tokens=1024,
                timeout_s=settings.LLM_TIMEOUT_SECONDS,
            )

            parsed = CoachFeedbackOutput.model_validate(tool_input)
            parsed.strength_hi = unicodedata.normalize("NFC", parsed.strength_hi)
            parsed.change_hi = unicodedata.normalize("NFC", parsed.change_hi)
            parsed.exact_words_hi = unicodedata.normalize("NFC", parsed.exact_words_hi)
            parsed.evidence = {
                k: unicodedata.normalize("NFC", v) for k, v in parsed.evidence.items()
            }

            is_valid, err_msg = guard_coach(
                output=parsed,
                rubric_criterion_ids=rubric_criterion_ids,
                teacher_transcript=transcript_str,
                rubric_rewards_not_telling=rubric_rewards_not_telling,
                current_item_answer=current_item_answer,
            )

            if is_valid:
                if parsed.confidence < settings.COACH_CONFIDENCE_THRESHOLD:
                    parsed.needs_review = True
                    logger.warning(
                        "Coach confidence (%.2f < %.2f) for ref_id %s; flagged needs_review",
                        parsed.confidence,
                        settings.COACH_CONFIDENCE_THRESHOLD,
                        ref_id,
                    )
                    create_coach_review_item(
                        ref_id=ref_id,
                        confidence=parsed.confidence,
                        reason=f"Coach confidence {parsed.confidence:.2f} below threshold",
                        db=db,
                    )
                return parsed

            logger.warning("coach guard failed (attempt %d): %s", attempt_idx + 1, err_msg)
            if attempt_idx == 0:
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            f"Your feedback failed validation: {err_msg}. Please fix the issue and adhere strictly to "
                            f"the rubric, word budget (<= 60 words across strength, change, and exact_words), and respectful 'आप' register."
                        ),
                    }
                )
        except (LLMUnavailable, NotImplementedError, Exception) as exc:
            logger.warning("coach LLM call failed (attempt %d): %s", attempt_idx + 1, exc)
            if attempt_idx == 1:
                break

    logger.info("Using deterministic fallback for coach feedback on move %s", move.id)
    fb = fallback_coach_feedback(
        move=move,
        transcript=transcript,
        act_tags=act_tags,
        child_trajectories=child_trajectories,
        current_item_answer=current_item_answer,
        attempt=attempt,
        previous_change_hi=previous_change_hi,
    )
    create_coach_review_item(
        ref_id=ref_id,
        confidence=fb.confidence,
        reason="Fallback coach used",
        db=db,
    )
    return fb
