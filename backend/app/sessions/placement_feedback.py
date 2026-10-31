"""The coach's line after the short onboarding practice: what she did, and why this first move.

Deterministic and catalogue-based (Hindi and English twins). It names the acts the tagger found in
her turns with Ravi, in a fixed order, then the reason for the first move.
"""

from __future__ import annotations

from collections.abc import Iterable

from backend.app.core.messages import get_message
from backend.app.rule_engine.domain import TeachingAct

_ASKED = {TeachingAct.ASK_TO_EXPLAIN, TeachingAct.PROBE_SIMPLER_CASE}
_WORDS = {TeachingAct.MODEL_STEP_ALOUD, TeachingAct.CONTRAST_TWO_ANSWERS}
_OBJECTS = {TeachingAct.CONCRETE_REPRESENTATION}
_TOLD = {TeachingAct.TELL_ANSWER}


def placement_feedback(
    acts: Iterable[str],
    move_title: str,
    address_form: str = "f",
    told_later: bool = False,
) -> str:
    """One specific feedback message from the acts of the onboarding scene.

    `told_later`: a turn after her first one dictated the procedure (found from her words, since
    the act tagger can miss it); it adds one line unless she is already told she gave the answer.
    """
    seen = {str(a) for a in acts}

    def has(group: set[TeachingAct]) -> bool:
        return any(a.value in seen for a in group)

    asked, objects, told = has(_ASKED), has(_OBJECTS), has(_TOLD)
    words = has(_WORDS) and not objects  # objects supersede words as the thing to praise
    parts: list[str] = []
    if asked:
        parts.append("placement_fb_asked")
    if words:
        parts.append("placement_fb_words")
    if objects:
        parts.append("placement_fb_objects")
    if told:
        parts.append("placement_fb_told")
    if not parts:
        parts.append("placement_fb_none")
    if told_later and not told:
        parts.append("placement_fb_told_later")
    why = (
        "placement_fb_why_told"
        if told
        else "placement_fb_why_words"
        if words
        else "placement_fb_why_objects"
        if objects
        else "placement_fb_why_default"
    )
    sentences = [get_message(k, address_form) for k in parts]
    sentences.append(get_message(why, address_form, move_title=move_title))
    return " ".join(sentences)


__all__ = ["placement_feedback"]
