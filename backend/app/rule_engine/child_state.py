from backend.app.rule_engine.domain import ChildState as ChildState

__all__ = ["ChildState", "TRANSITIONS"]

# Transition table per Section 5.2
TRANSITIONS: dict[str, dict[ChildState, ChildState] | str] = {
    "ask_to_explain": {ChildState.MISCONCEPTION: ChildState.CAN_EXPLAIN},
    "concrete_representation": {
        ChildState.CAN_EXPLAIN: ChildState.PARTIAL,
        ChildState.MISCONCEPTION: ChildState.PARTIAL,
    },
    "probe_simpler_case": {ChildState.CAN_EXPLAIN: ChildState.PARTIAL},
    "contrast_answers": {ChildState.PARTIAL: ChildState.CORRECT},
    "model_step_aloud": {ChildState.PARTIAL: ChildState.CORRECT},
    "tell_answer": "PARROT",  # repeats answer now, relapses on next item
    "repeat_question": "NO_CHANGE",
    "scold": "SHY",  # shy persona goes silent one turn
}
