"""A short talk-move line for the end-of-scene coach feedback.

Built only from the teacher's tagged turns (the acts the tagger already stored, and who each turn
was addressed to), never from a model, so it cannot drift from what she actually said. It counts
three things per scene: asked a named child vs the whole class (group scenes only), asked a child
to explain how or why vs only checked the answer, and told the answer. It gives one strength and
one next step. It does not measure wait time (no timing is recorded) and makes no claim beyond the
counts.

In a one-on-one scene the strength carries the teacher's own words in the same guillemet form the
coach strength already uses (`coach_quote_suffix`), so the chat shows the existing quote badge. A
group scene carries no quote, as in the coach feedback.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from backend.app.config import settings
from backend.app.core.intents import is_pedagogy_question_for_app
from backend.app.core.messages import get_message
from backend.app.rehearsal.scene_store import TurnRecord
from backend.app.rule_engine.domain import TeachingAct

_STOP = "stop"
_QUOTE_MARKS = "«»"
_EXPLAIN = TeachingAct.ASK_TO_EXPLAIN.value
_TOLD = TeachingAct.TELL_ANSWER.value
_CHECK = (TeachingAct.REPEAT_QUESTION.value, TeachingAct.GIVE_NEW_PROBLEM.value)
_WHOLE_CLASS = "all"


@dataclass(frozen=True)
class TalkMoveCounts:
    turns: int = 0
    named: int = 0  # group scenes: a turn addressed to one named child
    whole_class: int = 0  # group scenes: a turn addressed to everyone
    explain: int = 0  # asked a child how or why
    check_only: int = 0  # asked for an answer (repeat or new problem) without asking how or why
    told: int = 0  # gave the answer
    explain_quote_source: str = ""  # her first line that asked a child to explain


def count_turns(turns: Sequence[TurnRecord], *, one_on_one: bool) -> TalkMoveCounts:
    """Counts from the tagged teacher turns (stop commands and how-to questions to the app skipped)."""
    n = named = whole = explain = check = told = 0
    source = ""
    for turn in turns:
        text = (turn.transcript or "").strip()
        if not text or _STOP in turn.acts or is_pedagogy_question_for_app(text):
            continue
        n += 1
        if not one_on_one:
            if turn.addressed_child == _WHOLE_CLASS:
                whole += 1
            elif turn.addressed_child:
                named += 1
        if _EXPLAIN in turn.acts:
            explain += 1
            source = source or text
        elif any(a in turn.acts for a in _CHECK):
            check += 1
        if _TOLD in turn.acts:
            told += 1
    return TalkMoveCounts(n, named, whole, explain, check, told, source)


def _quote(text: str) -> str:
    """The first words of her own line, with no guillemets that would break the badge."""
    cleaned = "".join(ch for ch in text if ch not in _QUOTE_MARKS)
    return " ".join(cleaned.split()[: settings.COACH_QUOTE_MAX_WORDS])


def _strength_key(c: TalkMoveCounts, *, one_on_one: bool) -> str | None:
    if c.explain:
        return "tm_strength_explain"
    if not one_on_one and c.named:
        return "tm_strength_named"
    if not one_on_one and c.whole_class:
        return "tm_strength_class"
    return None


def _next_key(c: TalkMoveCounts, *, one_on_one: bool) -> str:
    if c.told:
        return "tm_next_told"
    if c.check_only and not c.explain:
        return "tm_next_check"
    if not one_on_one and c.whole_class and not c.named:
        return "tm_next_named"
    if not c.explain:
        return "tm_next_explain"
    return "tm_next_keep"


def talk_move_line(
    turns: Sequence[TurnRecord], *, one_on_one: bool, address_form: str = "f"
) -> str:
    """The heading, one strength (when there is one) and one next step; "" with no teacher turn."""
    c = count_turns(turns, one_on_one=one_on_one)
    if c.turns == 0:
        return ""
    lines = [get_message("tm_head", address_form)]
    strength = _strength_key(c, one_on_one=one_on_one)
    if strength is not None:
        text = get_message(strength, address_form)
        quote = (
            _quote(c.explain_quote_source)
            if one_on_one and strength == "tm_strength_explain"
            else ""
        )
        if quote:
            text = f"{text} {get_message('coach_quote_suffix', address_form, quote=quote)}"
        lines.append(f"👍 {text}")
    lines.append(f"➡️ {get_message(_next_key(c, one_on_one=one_on_one), address_form)}")
    return "\n".join(lines)


__all__ = ["TalkMoveCounts", "count_turns", "talk_move_line"]
