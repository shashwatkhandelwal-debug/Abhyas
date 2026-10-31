"""Child Voice role implementation matching spec/05 §5.5.

Renders rule engine ChildResponse into natural childlike Hindi speech
using Claude fast model (or MockLLM) with a deterministic template fallback.
"""

import difflib
import logging
import re
import time
import unicodedata
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from backend.app.config import settings
from backend.app.content_models import PersonaCard
from backend.app.llm.address import address_rule, address_word, fix_address
from backend.app.llm.client import LLMUnavailable, call_tool, log_role_call
from backend.app.llm.guard_stats import record_guard_event
from backend.app.llm.guards import child_line_word_cap, guard_child_line
from backend.app.llm.hindi_numbers import extract_numbers
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


_PUNCT = re.compile(r"[^\wऀ-ॿ\s]|_")
_ADDRESS_WORDS = frozenset({"सर", "दीदी", "मैडम", "मैम", "मेम", "madam", "sir"})


def _core_tokens(line: str) -> list[str]:
    """Words of a child line without punctuation, the address word and filler words (NFC)."""
    text = _PUNCT.sub(" ", unicodedata.normalize("NFC", line or "").casefold())
    skip = _ADDRESS_WORDS | set(settings.CHILD_REPEAT_FILLER_WORDS)
    return [w for w in text.split() if w not in skip]


def is_near_repeat(line: str, previous_line: str | None) -> bool:
    """True when `line` says (nearly) what the same child said last: same core words, or a
    token similarity of at least `CHILD_REPEAT_SIMILARITY`."""
    if not previous_line or not previous_line.strip():
        return False
    now, before = _core_tokens(line), _core_tokens(previous_line)
    if not now or not before:
        return _norm(line) == _norm(previous_line)
    if now == before:
        return True
    return difflib.SequenceMatcher(None, now, before).ratio() >= settings.CHILD_REPEAT_SIMILARITY


_TELLING_ACTS = frozenset({"tell_answer", "model_step_aloud"})


def teacher_is_telling(teacher_said: str | None, acts: Sequence[str] = ()) -> bool:
    """The teacher told or explained the steps (tagged, or: several numbers plus a procedure verb)."""
    if _TELLING_ACTS & {str(a) for a in acts}:
        return True
    text = teacher_said or ""
    if len(extract_numbers(text)) < settings.CHILD_TELLING_MIN_NUMBERS:
        return False
    return any(stem in text for stem in settings.CHILD_TELLING_VERB_STEMS)


def reaction_for(
    response: ChildResponse,
    teacher_said: str | None,
    acts: Sequence[str],
    previous_line: str | None,
) -> str | None:
    """ "telling" or "off_task" when the child must answer what the teacher just did, else None.

    Only a child holding on to a method (explain_bug, relapse, or a repeated answer) reacts this
    way; a child who got it right, parrots, or is a scripted distraction keeps the engine's line.
    """
    kind = response.kind
    if kind not in (ResponseKind.EXPLAIN_BUG, ResponseKind.RELAPSE, ResponseKind.ANSWER):
        return None
    if kind == ResponseKind.ANSWER and not previous_line:
        return None
    if "off_task" in {str(a) for a in acts}:
        return "off_task"
    if teacher_is_telling(teacher_said, acts):
        return "telling"
    return None


# What a child says when the teacher told him the steps, or drifted off the question: he reacts
# to it, says no number, and keeps his own mistake (no gendered verb: used for every child).
_REACTION_LINES: dict[str, tuple[str, ...]] = {
    "telling": (
        "मुझे ठीक से समझ नहीं आया। पहला कदम फिर से बताइए?",
        "आपने जो कहा, उसमें एक जगह मेरा काम अटक गया। वहाँ क्या करना है?",
        "हम्म… थोड़ा-सा समझ आया, पर आगे क्या करना है, पता नहीं।",
        "इतनी जल्दी-जल्दी मुझे समझ नहीं आया, धीरे से बताइए?",
    ),
    "off_task": (
        "आपने क्या कहा? मुझे तो सवाल वाली बात ही याद है।",
        "ये तो सवाल से अलग बात है। पहले सवाल पर बात करें?",
        "हम्म… अभी तो सवाल चल रहा है, उसी पर बात करें?",
    ),
}


def reaction_template(
    reaction: str, turn_idx: int, address_form: str | None, previous_line: str | None
) -> str:
    """The template-path line for a reaction state; never a near-repeat of the previous line."""
    pool = _REACTION_LINES[reaction]
    word = address_word(address_form)
    lines = [fix_address(f"{word}, {t}" if word else t, address_form) for t in pool]
    for k in range(len(lines)):
        candidate = lines[(turn_idx + k) % len(lines)]
        if not is_near_repeat(candidate, previous_line):
            return candidate
    return lines[turn_idx % len(lines)]


# Short restatements of the child's own answer, used when every fuller variant would repeat him.
_RESTATE_SHORT: tuple[str, ...] = (
    "मैंने तो यही किया था। {a}!",
    "{a} आया, मुझे तो यही लगता है।",
    "मैंने ध्यान से किया, {a}!",
)


def template_line(
    response: ChildResponse,
    persona: PersonaCard | None = None,
    turn_idx: int = 0,
    address_form: str | None = "f",
    previous_line: str | None = None,
) -> str:
    """Deterministic template fallback line for a child response (spec/05 §5.5).

    Returns guaranteed guard-compliant Hindi text for every ResponseKind:
    - ANSWER: "{answer}!"
    - EXPLAIN_BUG / RELAPSE / CORRECT_EXPLAINED: join steps with "। " + "। {answer}!"
    - SCAFFOLDED_CORRECT: "हम्म… " + steps + "। {answer}!"
    - PARROT: "{answer}… ?"
    - SILENT: ""
    - OFF_TOPIC / INTERJECT: persona off_topic line or default childlike remark
    - CONFUSED: "<दीदी or सर>, ये तो बहुत बड़ा है… समझ नहीं आया।" (no address word if unknown)

    The address word follows `address_form` (f: दीदी, m: सर, unknown: none); see `fix_address`.
    Given `previous_line` (this child's last line), the line differs from it: the variants in
    `_VARIANTS` are tried in order, plain line first, and only guard-clean ones are used.
    """
    word = address_word(address_form)
    base = fix_address(_template_line(response, persona, turn_idx, word), address_form)
    if not previous_line or not base:
        return base
    for lead, tail in _VARIANTS.get(response.kind, ()):
        candidate = _variant(base, response, lead, tail)
        fixed = fix_address(candidate, address_form)
        if not is_near_repeat(fixed, previous_line) and guard_child_line(candidate, response)[0]:
            return fixed
    if response.answer is not None and response.kind not in (
        ResponseKind.OFF_TOPIC,
        ResponseKind.INTERJECT,
        ResponseKind.CONFUSED,
    ):
        for k in range(len(_RESTATE_SHORT)):
            short = _RESTATE_SHORT[(turn_idx + k) % len(_RESTATE_SHORT)].format(a=response.answer)
            fixed = fix_address(short, address_form)
            if not is_near_repeat(fixed, previous_line) and guard_child_line(short, response)[0]:
                return fixed
    return base


# (lead-in, ending) pairs per kind; ("", "") is the plain line. No numbers, no digressions.
_VARIANTS: dict[ResponseKind, tuple[tuple[str, str], ...]] = {
    ResponseKind.ANSWER: (("", ""), ("मेरा तो ", " आया!"), ("", " ही है!"), ("मुझे तो ", " आया।")),
    ResponseKind.EXPLAIN_BUG: (("", ""), ("देखो, ", ""), ("मैंने तो ऐसे किया: ", ""), ("सुनो, ", "")),
    ResponseKind.RELAPSE: (("", ""), ("देखो, ", ""), ("मैंने तो ऐसे किया: ", ""), ("सुनो, ", "")),
    ResponseKind.CORRECT_EXPLAINED: (("", ""), ("देखो, ", ""), ("सुनो, ", "")),
    ResponseKind.SCAFFOLDED_CORRECT: (("", ""), ("हम्म, देखो… ", ""), ("सोचने दो… ", "")),
    ResponseKind.PARROT: (("", ""), ("हम्म… ", ""), ("सच में? ", "")),
}


def _norm(line: str) -> str:
    return " ".join(line.split())


def _variant(base: str, response: ChildResponse, lead: str, tail: str) -> str:
    """`base` with a lead-in; a bare answer line is rebuilt around the answer instead."""
    if response.kind == ResponseKind.ANSWER:
        return f"{lead}{response.answer}{tail or '!'}"
    return f"{lead}{base}"


def _template_line(
    response: ChildResponse,
    persona: PersonaCard | None,
    turn_idx: int,
    teacher_address: str,
) -> str:

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
        return f"{teacher_address + ', ' if teacher_address else ''}ये तो बहुत बड़ा है… समझ नहीं आया।"

    if response.kind in (ResponseKind.OFF_TOPIC, ResponseKind.INTERJECT):
        if persona and persona.off_topic_lines_hi:
            return persona.off_topic_lines_hi[turn_idx % len(persona.off_topic_lines_hi)]
        return f"{teacher_address + ', ' if teacher_address else ''}बाहर तितली उड़ रही है!"

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


def _required_in_line(sentence: str, response: ChildResponse) -> bool:
    """True if this sentence carries the answer (the part a cut must never drop)."""
    if isinstance(response.answer, int):
        return response.answer in extract_numbers(sentence)
    if isinstance(response.answer, str) and response.answer:
        return response.answer.replace(" ", "") in sentence.replace(" ", "")
    return False


def shorten_keeping_required(line: str, max_words: int, response: ChildResponse) -> str:
    """Shortens `line` to `max_words` without dropping the sentence(s) holding the answer.

    Answer sentences are kept first, then earlier sentences are added back in order while they
    fit. If the answer sentence alone is too long, falls back to the plain sentence cut.
    """
    if len(line.split()) <= max_words:
        return line.strip()
    sentences = _SENTENCE_END.split(line.strip())
    required = {i for i, s in enumerate(sentences) if _required_in_line(s, response)}
    if not required:
        return truncate_at_sentence_boundary(line, max_words)
    budget = max_words - sum(len(sentences[i].split()) for i in required)
    if budget < 0:
        return truncate_at_sentence_boundary(line, max_words)
    keep = set(required)
    for i, s in enumerate(sentences):
        n = len(s.split())
        if i not in keep and n <= budget:
            keep.add(i)
            budget -= n
    return " ".join(sentences[i] for i in sorted(keep))


def _script_lines(response: ChildResponse, steps_text: str) -> str:
    """The "what the child says" bullets; a missing answer or steps is omitted, never a placeholder."""
    lines: list[str] = []
    if response.answer is not None:
        lines.append(f"- answer: {response.answer}")
    if steps_text:
        lines.append(
            "- reasoning steps to express (in this order, compress freely, but keep every "
            f"number): {steps_text}"
        )
    return "\n".join(lines)


def _answer_rule(response: ChildResponse) -> str:
    if response.kind in (ResponseKind.OFF_TOPIC, ResponseKind.INTERJECT, ResponseKind.CONFUSED):
        return "Say NO number at all."
    if response.answer is None:
        return "Say no number at all."
    return f"You MUST say the answer {response.answer}, and finish the line with it."


def _no_repeat_rule(previous_line: str | None) -> str:
    """The prompt sentence that stops the child repeating himself while keeping the same mistake."""
    if not previous_line or not previous_line.strip():
        return ""
    return (
        f"\nYour previous line in this scene was: «{_norm(previous_line)}»\n"
        "Do not repeat it. React to what the teacher just said, in new words, while keeping the "
        "same mistake. If she asked a concrete question (about a letter, a matra, a number, an "
        "object), answer exactly that question in your own words. If she explained a method in "
        "words, say which part you did not follow. Never use a stock sentence about doing it "
        "your own way. Use only the numbers you are allowed."
    )


async def voice_child_line(
    response: ChildResponse,
    persona: PersonaCard,
    last_4_lines: list[str] | None = None,
    turn_idx: int = 0,
    address_form: str | None = "f",
    previous_line: str | None = None,
    teacher_said: str | None = None,
    teacher_acts: Sequence[str] = (),
) -> str:
    """One child line, with the address word forced to the teacher's form (text-only last check).

    `previous_line` is this child's last line in the scene; the new line is never identical to it.
    `teacher_said` is what the teacher just said, so the child can react to it, and
    `teacher_acts` the acts the tagger found in it (telling or drifting off makes him react).
    """
    line = await _voice_child_line(
        response,
        persona,
        last_4_lines,
        turn_idx,
        address_form,
        previous_line,
        teacher_said,
        teacher_acts,
    )
    return fix_address(line, address_form)


async def _voice_child_line(
    response: ChildResponse,
    persona: PersonaCard,
    last_4_lines: list[str] | None,
    turn_idx: int,
    address_form: str | None,
    previous_line: str | None,
    teacher_said: str | None,
    teacher_acts: Sequence[str] = (),
) -> str:
    """Voices one child line using Claude fast model, with guard and template fallback.

    Strictly implements spec/05 §5.2 role contract pattern:
    - SILENT returns "" immediately without calling Claude.
    - Other kinds: build_input -> call_tool -> validate -> guard -> retry once on error -> template fallback.
    """
    if response.kind == ResponseKind.SILENT:
        return ""
    if response.kind == ResponseKind.CONFUSED:
        # Out-of-range problem: the child just says it is too big. Nothing to voice, no answer.
        return template_line(response, persona, turn_idx, address_form, previous_line)

    reaction = reaction_for(response, teacher_said, teacher_acts, previous_line)
    if reaction is not None:
        # The teacher told him the steps (or drifted): he reacts to that, with no number, instead
        # of restating his method. Voiced as a "confused" line, so the guard allows no new answer.
        response = response.model_copy(update={"kind": ResponseKind.CONFUSED, "answer": None})

    prompt_path = Path(__file__).resolve().parent.parent / "prompts" / f"{PROMPT_VERSION}.md"
    if prompt_path.exists():
        system_template = prompt_path.read_text(encoding="utf-8")
    else:
        system_template = "You voice a child line. Return tool call."

    max_words = child_line_word_cap(response.kind)
    # Hand the model steps already compressed to fit the cap, so it does not pad and overrun.
    steps_text = _format_steps(response.steps, max_words=max_words - 10) if response.steps else ""
    script_lines = _script_lines(response, steps_text)
    if reaction is not None:
        script_lines = (
            "- the teacher just "
            + ("told you the steps" if reaction == "telling" else "said something off the question")
            + ": answer THAT. Say you tried to follow and got stuck, or ask about one step, or say "
            "you are confused. Do not restate your own method or any answer."
        )

    system_prompt = system_template.format(
        name=persona.name_hi,
        temperament=persona.temperament,
        speech_style_hi=persona.speech_style_hi,
        affect=response.affect,
        kind=response.kind.value,
        script_lines=script_lines,
        answer_rule=_answer_rule(response),
        max_words=max_words,
        allowed_numbers=sorted(response.allowed_numbers),
        forbidden=sorted(response.forbidden),
        address_rule=address_rule(address_form),
        no_repeat_rule=_no_repeat_rule(previous_line),
    )

    context_lines = "\n".join(last_4_lines) if last_4_lines else "कक्षा में अभ्यास चल रहा है।"
    said = ""
    if teacher_said and teacher_said.strip():
        said = (
            f"The teacher just said: «{_norm(teacher_said)[: settings.TEACHER_SAID_MAX_CHARS]}»\n\n"
        )
    user_message = (
        f"Recent dialogue in classroom:\n{context_lines}\n\n{said}"
        f"Voice {persona.name_hi}'s next line."
    )
    messages: list[dict[str, Any]] = [{"role": "user", "content": user_message}]

    # 2. Attempt LLM call with retry per §5.2
    started = time.perf_counter()
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
            if is_valid and reaction is not None and extract_numbers(parsed.line_hi):
                is_valid, err_msg = False, "react to the teacher without any number or answer"
            if is_valid and is_near_repeat(
                fix_address(parsed.line_hi, address_form), previous_line
            ):
                is_valid, err_msg = False, "too close to your previous line (say it differently)"
            if is_valid:
                latency_ms = int((time.perf_counter() - started) * 1000)
                logger.info(
                    "child_voice_reply_latency turn=%d persona=%s latency_ms=%d fallback_used=false",
                    turn_idx,
                    persona.id,
                    latency_ms,
                )
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
                candidate = shorten_keeping_required(parsed.line_hi, max_words, response)
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
        latency_ms = int((time.perf_counter() - started) * 1000)
        logger.info(
            "child_voice_reply_latency turn=%d persona=%s latency_ms=%d fallback_used=false",
            turn_idx,
            persona.id,
            latency_ms,
        )
        log_role_call("child_voice", settings.CLAUDE_MODEL_FAST, started, False)
        return shortened

    # 4. Deterministic template fallback
    logger.info("Using template fallback for child voice line")
    latency_ms = int((time.perf_counter() - started) * 1000)
    logger.info(
        "child_voice_reply_latency turn=%d persona=%s latency_ms=%d fallback_used=true",
        turn_idx,
        persona.id,
        latency_ms,
    )
    log_role_call("child_voice", settings.CLAUDE_MODEL_FAST, started, True)
    if reaction is not None:
        return reaction_template(reaction, turn_idx, address_form, previous_line)
    return template_line(
        response=response,
        persona=persona,
        turn_idx=turn_idx,
        address_form=address_form,
        previous_line=previous_line,
    )
