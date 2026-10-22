"""Child Voice role implementation matching spec/05 §5.5.

Renders rule engine ChildResponse into natural childlike Hindi speech
using Claude fast model (or MockLLM) with a deterministic template fallback.
"""

import logging
import re
import time
from pathlib import Path
from typing import Any

from backend.app.config import settings
from backend.app.content_models import PersonaCard
from backend.app.llm.client import LLMUnavailable, call_tool, log_role_call
from backend.app.llm.guard_stats import record_guard_event
from backend.app.llm.guards import guard_child_line
from backend.app.llm.schemas import ChildVoiceOutput
from backend.app.rule_engine.domain import ChildResponse, ResponseKind

logger = logging.getLogger("abhyas.llm.child_voice")

PROMPT_VERSION = "child_voice.v1"


def _format_steps(steps: list[Any], max_words: int) -> str:
    """Formats steps ensuring total words do not exceed max_words."""
    # Filter out redundant answer steps if present
    step_texts = [s.text_hi for s in steps if s.code != "ANSWER"]
    if not step_texts:
        return ""
    # Try including all steps
    candidate = "। ".join(step_texts)
    if len(candidate.split()) <= max_words:
        return candidate
    # If too long, omit setup steps first
    calc_steps = [s.text_hi for s in steps if s.code not in ("ANSWER", "SUB_CANNOT")]
    candidate = "। ".join(calc_steps)
    if len(candidate.split()) <= max_words:
        return candidate
    # Otherwise take steps from the end until they fit
    selected: list[str] = []
    for text in reversed(calc_steps):
        test_candidate = "। ".join([text] + selected)
        if len(test_candidate.split()) <= max_words:
            selected.insert(0, text)
        else:
            break
    return "। ".join(selected)


def template_line(
    response: ChildResponse,
    persona: PersonaCard | None = None,
    turn_idx: int = 0,
    address_form: str = "f",
) -> str:
    """Deterministic template fallback line for a child response (spec/05 §5.5).

    Returns guaranteed guard-compliant Hindi text for every ResponseKind:
    - ANSWER: "{answer}!"
    - EXPLAIN_BUG / RELAPSE / CORRECT_EXPLAINED: join steps with "। " + "। {answer}!"
    - SCAFFOLDED_CORRECT: "हम्म… " + steps + "। {answer}!"
    - PARROT: "{answer}… ?"
    - SILENT: ""
    - OFF_TOPIC / INTERJECT: persona off_topic line or default childlike remark
    - CONFUSED: "दीदी/सर, ये तो बहुत बड़ा है… समझ नहीं आया।"
    """
    teacher_address = "सर" if address_form == "m" else "दीदी"

    if response.kind == ResponseKind.SILENT:
        return ""

    if response.kind == ResponseKind.ANSWER:
        return f"{response.answer}!"

    if response.kind == ResponseKind.PARROT:
        return f"{response.answer}… ?"

    if response.kind in (
        ResponseKind.EXPLAIN_BUG,
        ResponseKind.RELAPSE,
        ResponseKind.CORRECT_EXPLAINED,
    ):
        if response.steps:
            steps_joined = _format_steps(response.steps, max_words=22)
            if steps_joined:
                return f"{steps_joined}। {response.answer}!"
        return f"{response.answer}!"

    if response.kind == ResponseKind.SCAFFOLDED_CORRECT:
        if response.steps:
            steps_joined = _format_steps(response.steps, max_words=20)
            if steps_joined:
                return f"हम्म… {steps_joined}। {response.answer}!"
        return f"हम्म… {response.answer}!"

    if response.kind == ResponseKind.CONFUSED:
        return f"{teacher_address}, ये तो बहुत बड़ा है… समझ नहीं आया।"

    if response.kind in (ResponseKind.OFF_TOPIC, ResponseKind.INTERJECT):
        if persona and persona.off_topic_lines_hi:
            line = persona.off_topic_lines_hi[turn_idx % len(persona.off_topic_lines_hi)]
            if address_form == "m":
                line = line.replace("दीदी", "सर").replace("मैडम", "सर")
            return line
        return f"{teacher_address}, बाहर तितली उड़ रही है!"

    # Default fallback
    return f"{response.answer}!" if response.answer is not None else ""


_SENTENCE_END = re.compile(r"(?<=[।?!])\s+")


def truncate_at_sentence_boundary(line: str, max_words: int) -> str:
    """Shortens `line` to at most `max_words`, keeping whole sentences when possible.

    Falls back to a hard cut at a word boundary only if the first sentence alone is too long.
    """
    if len(line.split()) <= max_words:
        return line.strip()
    kept: list[str] = []
    words = 0
    for sentence in _SENTENCE_END.split(line.strip()):
        n = len(sentence.split())
        if words + n > max_words:
            break
        kept.append(sentence)
        words += n
    if kept:
        return " ".join(kept)
    return " ".join(line.split()[:max_words]).rstrip(",…-") + "…"


async def voice_child_line(
    response: ChildResponse,
    persona: PersonaCard,
    last_4_lines: list[str] | None = None,
    turn_idx: int = 0,
    address_form: str = "f",
) -> str:
    """Voices one child line using Claude fast model, with guard and template fallback.

    Strictly implements spec/05 §5.2 role contract pattern:
    - SILENT returns "" immediately without calling Claude.
    - Other kinds: build_input -> call_tool -> validate -> guard -> retry once on error -> template fallback.
    """
    if response.kind == ResponseKind.SILENT:
        return ""

    prompt_path = Path(__file__).resolve().parent.parent / "prompts" / f"{PROMPT_VERSION}.md"
    if prompt_path.exists():
        system_template = prompt_path.read_text(encoding="utf-8")
    else:
        system_template = "You voice a child line. Return tool call."

    teacher_address = "सर" if address_form == "m" else "दीदी"
    steps_text = (
        " -> ".join(f"{s.text_hi}" for s in response.steps) if response.steps else "कोई कदम नहीं"
    )

    system_prompt = system_template.format(
        name=persona.name_hi,
        temperament=persona.temperament,
        speech_style_hi=persona.speech_style_hi,
        affect=response.affect,
        kind=response.kind.value,
        answer=response.answer if response.answer is not None else "कोई उत्तर नहीं",
        steps_text=steps_text,
        allowed_numbers=sorted(response.allowed_numbers),
        forbidden=sorted(response.forbidden),
        teacher_address=teacher_address,
    )

    context_lines = "\n".join(last_4_lines) if last_4_lines else "कक्षा में अभ्यास चल रहा है।"
    user_message = (
        f"Recent dialogue in classroom:\n{context_lines}\n\nVoice {persona.name_hi}'s next line."
    )
    messages: list[dict[str, Any]] = [{"role": "user", "content": user_message}]

    # 2. Attempt LLM call with retry per §5.2
    started = time.perf_counter()
    max_words = settings.MAX_CHILD_LINE_WORDS
    shortened: str | None = None  # guard-clean truncation of an over-long attempt
    for attempt in range(2):
        try:
            tool_input = await call_tool(
                role="child_voice",
                model=settings.CLAUDE_MODEL_FAST,
                system=system_prompt,
                messages=messages,
                tool_name="child_voice",
                input_schema=ChildVoiceOutput.model_json_schema(),
                temperature=0.4,
                max_tokens=settings.CHILD_VOICE_MAX_TOKENS,
                timeout_s=settings.LLM_TIMEOUT_SECONDS,
            )

            parsed = ChildVoiceOutput.model_validate(tool_input)
            is_valid, err_msg = guard_child_line(parsed.line_hi, response)
            record_guard_event("child_voice", attempt, is_valid, err_msg)
            if is_valid:
                log_role_call("child_voice", settings.CLAUDE_MODEL_FAST, started, False)
                return parsed.line_hi

            logger.warning("child_voice guard failed (attempt %d): %s", attempt + 1, err_msg)
            feedback = f"Your previous line failed a check: {err_msg}. Follow the hard rules."
            n_words = len(parsed.line_hi.split())
            if n_words > max_words:
                feedback = (
                    f"Your previous line was {n_words} words: «{parsed.line_hi}». "
                    f"Shorten it to at most {max_words} words; keep the answer and every required "
                    "number, and drop any unrelated remark."
                )
                candidate = truncate_at_sentence_boundary(parsed.line_hi, max_words)
                if guard_child_line(candidate, response)[0]:
                    shortened = candidate
            if attempt == 0:
                messages.append({"role": "user", "content": feedback})
        except (LLMUnavailable, NotImplementedError, Exception) as exc:
            logger.warning("child_voice LLM call failed (attempt %d): %s", attempt + 1, exc)
            if attempt == 0:
                messages.append(
                    {
                        "role": "user",
                        "content": "Your previous reply was empty or incomplete. Return the "
                        f"line_hi field, at most {max_words} words.",
                    }
                )

    # 3. Keep the model's own words (cut at a sentence boundary) before any template
    if shortened is not None:
        logger.info("Truncated over-long child voice line at sentence boundary")
        log_role_call("child_voice", settings.CLAUDE_MODEL_FAST, started, False)
        return shortened

    # 4. Deterministic template fallback
    logger.info("Using template fallback for child voice line")
    log_role_call("child_voice", settings.CLAUDE_MODEL_FAST, started, True)
    return template_line(
        response=response,
        persona=persona,
        turn_idx=turn_idx,
        address_form=address_form,
    )
