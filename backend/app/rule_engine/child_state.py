"""Child state and transition logic as specified in Section 5.2."""

from enum import Enum
from typing import Any, Union


class ChildState(Enum):
    MISCONCEPTION = 0      # applies bug rule, confident
    CAN_EXPLAIN = 1        # still wrong, but explains steps (reveals the bug)
    PARTIAL = 2            # corrects with scaffold, may relapse on a new item
    CORRECT = 3            # correct and explains why


# Transition table per Section 5.2
TRANSITIONS: dict[str, Union[dict[ChildState, ChildState], str]] = {
    "ask_to_explain": {
        ChildState.MISCONCEPTION: ChildState.CAN_EXPLAIN
    },
    "concrete_representation": {
        ChildState.CAN_EXPLAIN: ChildState.PARTIAL,
        ChildState.MISCONCEPTION: ChildState.PARTIAL,
    },
    "probe_simpler_case": {
        ChildState.CAN_EXPLAIN: ChildState.PARTIAL
    },
    "contrast_answers": {
        ChildState.PARTIAL: ChildState.CORRECT
    },
    "model_step_aloud": {
        ChildState.PARTIAL: ChildState.CORRECT
    },
    "tell_answer": "PARROT",     # repeats answer now, relapses on next item
    "repeat_question": "NO_CHANGE",
    "scold": "SHY",              # shy persona goes silent one turn
}
