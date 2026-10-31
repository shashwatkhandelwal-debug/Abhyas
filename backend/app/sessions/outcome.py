"""The first line of the coach feedback: what happened in the scene, in plain words.

Built only from the tagged acts and the rule engine's recorded responses, never from a model, so it
cannot drift from what the children actually did. The coach's own advice follows it.
"""

from __future__ import annotations

from collections.abc import Sequence

from backend.app.content_models import Domain
from backend.app.core.messages import get_message
from backend.app.core.pronouns import child_pronouns
from backend.app.rehearsal.scene_store import TurnRecord
from backend.app.rule_engine.domain import ResponseKind, TeachingAct

# Most telling first: telling the answer teaches nothing, so it is named before anything good
_PRIORITY: tuple[tuple[ResponseKind, str], ...] = (
    (ResponseKind.PARROT, "coach_outcome_told"),
    (ResponseKind.RELAPSE, "coach_outcome_relapse"),
    (ResponseKind.CORRECT_EXPLAINED, "coach_outcome_checked"),
    (ResponseKind.SCAFFOLDED_CORRECT, "coach_outcome_concrete"),
    (ResponseKind.EXPLAIN_BUG, "coach_outcome_explain"),
)


# Where the numeracy wording (bundles and sticks) would be wrong for the move's domain
_LITERACY_KEYS = {"coach_outcome_concrete": "coach_outcome_concrete_literacy"}


def _told_before(turns: Sequence[TurnRecord], current: TurnRecord) -> bool:
    """True when the coach told the answer in this turn or an earlier one."""
    told = TeachingAct.TELL_ANSWER.value
    return any(told in t.acts for t in turns if t.turn_index <= current.turn_index)


def outcome_line(
    turns: Sequence[TurnRecord], address_form: str = "f", domain: Domain | None = None
) -> str:
    """One sentence naming the main thing that happened, or "" when nothing stands out."""
    for kind, key in _PRIORITY:
        for turn in turns:
            for response in turn.child_responses:
                if response.kind == kind:
                    if kind == ResponseKind.RELAPSE and not _told_before(turns, turn):
                        key = "coach_outcome_relapse_scaffold"
                    child = get_message(f"speaker_{response.persona_id}", address_form)
                    if domain == Domain.LITERACY:
                        key = _LITERACY_KEYS.get(key, key)
                    return get_message(
                        key, address_form, child=child, **child_pronouns(response.persona_id)
                    )
    return ""


_MISTAKE_KINDS = (ResponseKind.EXPLAIN_BUG, ResponseKind.RELAPSE)


def class_link_key(turns: Sequence[TurnRecord], persona_id: str, domain: Domain | None) -> str:
    """Catalog key for the line tying her class's struggle to this practice.

    It only says "same as X's mistake" when X really made it in this scene (a child who read or
    answered correctly did not), and it only talks about real objects outside literacy moves.
    """
    made = any(
        r.persona_id == persona_id and r.kind in _MISTAKE_KINDS
        for t in turns
        for r in t.child_responses
    )
    key = "coach_class_link" if made else "coach_class_link_general"
    return f"{key}_literacy" if domain == Domain.LITERACY else key
