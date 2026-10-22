"""The one-on-one chat header: child, progress cue, turn counter (all from the engine state).

The progress cue comes from the rule engine's child state, never from an LLM. Strings are in the
language of the current request.
"""

from __future__ import annotations

from typing import Any

from backend.app.core.messages import get_message
from backend.app.rule_engine.domain import Problem, SceneState

DIAGNOSE_CUE_STATE = -1  # state number sent while the teacher has not diagnosed yet


def board_text(item: Problem) -> str:
    if item.type == "sub":
        return f"{item.a} − {item.b}"
    if item.type == "add":
        return f"{item.a} + {item.b}"
    if item.type == "place_value":
        return f"{item.tens} × 10 + {item.ones}"
    return str(item.word or "")


def scene_header(
    scene_state: SceneState | dict[str, Any], active: bool = True
) -> dict[str, Any] | None:
    """Header data for an active one-on-one scene; None for group scenes and ended scenes."""
    state = (
        scene_state
        if isinstance(scene_state, SceneState)
        else SceneState.model_validate(scene_state)
    )
    if not active or state.ended or not state.one_on_one or not state.children:
        return None
    child = state.children[0]
    name = get_message(f"speaker_{child.persona_id}")
    cue_state = DIAGNOSE_CUE_STATE if state.diagnosing else int(child.state)
    cue_key = "ui_scene_cue_diagnose" if state.diagnosing else f"ui_scene_cue_{cue_state}"
    turn = min(state.teacher_turns, state.max_turns)
    return {
        "mode": "one_on_one",
        "child_id": child.persona_id,
        "child_name": name,
        "title": get_message("ui_scene_one_title", child=name),
        "cue": get_message(cue_key),
        "cue_state": cue_state,
        "turn": turn,
        "max_turns": state.max_turns,
        "turn_label": get_message("ui_scene_turn", turn=turn, max=state.max_turns),
        "board": board_text(state.current_item),
    }
