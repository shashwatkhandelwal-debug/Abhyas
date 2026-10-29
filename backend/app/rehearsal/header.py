"""The chat's scene bar: who she is talking to, the board problem and her turn counter.

Everything comes from the engine state, in the language of the current request. With
CHILD_STRIP_ENABLED (on in demo mode) each child also carries a small state label; with it off
the teacher finds out only by asking, which is the practice.
"""

from __future__ import annotations

from typing import Any

from backend.app.config import settings, v2_enabled
from backend.app.content_models import MoveCard
from backend.app.core.messages import get_message
from backend.app.rule_engine.bugs.registry import get_rule_info
from backend.app.rule_engine.child_state import ChildState
from backend.app.rule_engine.domain import ChildRuntime, Problem, SceneState


def item_dict(item: Problem) -> dict[str, Any]:
    """The board item's numbers or word, for the example line she can tap."""
    return {
        "type": item.type,
        "a": item.a,
        "b": item.b,
        "tens": item.tens,
        "ones": item.ones,
        "word": item.word,
    }


def manipulatives_dict(
    item: Problem, children: list[ChildRuntime] | None = None
) -> dict[str, Any] | None:
    """Manipulatives (bundles and sticks) for CRA concrete representation.

    Rendered strictly for subtraction problems when a < 100 and a >= 10.
    Regrouping applies only when units(a) < units(b) and a child in the scene
    has reached PARTIAL or CORRECT specifically on this item.
    """
    if item.type != "sub" or item.a is None or item.a >= 100 or item.a < 10:
        return None

    tens = item.a // 10
    ones = item.a % 10
    b_ones = (item.b % 10) if item.b is not None else 0
    needs_regroup = ones < b_ones

    item_key = item.key()
    is_regrouped = False
    if needs_regroup and children:
        is_regrouped = any(
            c.state in (ChildState.PARTIAL, ChildState.CORRECT) and c.partial_item_key == item_key
            for c in children
        )

    display_bundles = (tens - 1) if is_regrouped else tens
    display_sticks = (ones + 10) if is_regrouped else ones

    if is_regrouped:
        aria_label = f"{display_bundles} बंडल और {display_sticks} तीलियाँ (1 बंडल खुला)"
    else:
        aria_label = f"{display_bundles} बंडल और {display_sticks} तीलियाँ"

    return {
        "bundles": display_bundles,
        "sticks": display_sticks,
        "regrouped": is_regrouped,
        "aria_label": aria_label,
    }


def board_text(item: Problem) -> str:
    if item.type == "sub":
        return f"{item.a} − {item.b}"
    if item.type == "add":
        return f"{item.a} + {item.b}"
    if item.type == "place_value":
        return f"{item.tens} × 10 + {item.ones}"
    return str(item.word or "")


_FEMALE_PERSONAS = {"priya"}
_STRIP_KEY = {
    ChildState.MISCONCEPTION: "stuck",
    ChildState.CAN_EXPLAIN: "stuck",
    ChildState.PARTIAL: "learning",
    ChildState.CORRECT: "got",
}


def _relapsed(child: ChildRuntime, state: SceneState) -> bool:
    """A PARTIAL child who gives the bug answer on a new problem (the engine's relapse)."""
    if child.state != ChildState.PARTIAL or child.partial_item_key is None:
        return False
    if child.partial_item_key == state.current_item.key() or child.last_answer is None:
        return False
    try:
        rule = get_rule_info(child.misconception)
    except KeyError:  # an unknown bug id never breaks the scene bar
        return False
    bug = rule.fn(state.current_item, {"guess_lexicon": state.guess_lexicon})
    return str(child.last_answer) == str(bug.answer)


def child_strip_label(child: ChildRuntime, state: SceneState) -> str:
    """The small label beside a child's name, from existing scene state only (no engine change).

    MISCONCEPTION and CAN_EXPLAIN are both still wrong, so both read "stuck"; PARTIAL is "getting
    it"; CORRECT is "got it". A relapse adds the "stuck again" marker. A child who was only told
    the answer leaves no trace in the saved state, so that case shows as plain "stuck".
    """
    suffix = "_f" if child.persona_id in _FEMALE_PERSONAS else "_m"
    label = get_message(f"ui_strip_{_STRIP_KEY[child.state]}{suffix}")
    if _relapsed(child, state):
        label = f"{label} · {get_message(f'ui_strip_relapse{suffix}')}"
    return label


def scene_header(
    scene_state: SceneState | dict[str, Any], active: bool = True
) -> dict[str, Any] | None:
    """Scene bar data for an active scene (one-on-one or group); None when none is running."""
    state = (
        scene_state
        if isinstance(scene_state, SceneState)
        else SceneState.model_validate(scene_state)
    )
    if not active or state.ended or not state.children:
        return None
    strip = v2_enabled(settings.CHILD_STRIP_ENABLED)
    turn = min(state.teacher_turns, state.max_turns)
    header: dict[str, Any] = {
        "turn": turn,
        "max_turns": state.max_turns,
        "turn_label": get_message("ui_scene_turn", turn=turn, max=state.max_turns),
        "board": board_text(state.current_item),
        "item": item_dict(state.current_item),
        "manipulatives": manipulatives_dict(state.current_item, state.children),
    }
    if state.one_on_one or len(state.children) == 1:
        child = state.children[0]
        name = get_message(f"speaker_{child.persona_id}")
        return {
            **header,
            "mode": "one_on_one",
            "child_id": child.persona_id,
            "child_name": name,
            "title": get_message("ui_scene_one_title", child=name),
            "children": [],
            **({"strip_label": child_strip_label(child, state)} if strip else {}),
        }
    return {
        **header,
        "mode": "group",
        "title": get_message("ui_scene_group_title"),
        "children": [
            {
                "id": c.persona_id,
                "name": get_message(f"speaker_{c.persona_id}"),
                **({"label": child_strip_label(c, state)} if strip else {}),
            }
            for c in state.children
        ],
    }


def preview_header(move: MoveCard) -> dict[str, Any]:
    """The group scene bar before her first line (the scene record is created on that first turn)."""
    first = move.scenario.items[0] if move.scenario.items else {}
    item = Problem(
        type=first.get("type", "sub"),
        a=first.get("a"),
        b=first.get("b"),
        tens=first.get("tens"),
        ones=first.get("ones"),
        word=first.get("word"),
    )
    return {
        "mode": "group",
        "turn": 0,
        "max_turns": settings.MAX_TURNS_PER_REHEARSAL,
        "turn_label": get_message("ui_scene_turn", turn=0, max=settings.MAX_TURNS_PER_REHEARSAL),
        "board": board_text(item),
        "item": item_dict(item),
        "manipulatives": manipulatives_dict(item, None),
        "title": get_message("ui_scene_group_title"),
        "children": [
            {"id": c.persona_id, "name": get_message(f"speaker_{c.persona_id}")}
            for c in move.scenario.children
        ],
    }
