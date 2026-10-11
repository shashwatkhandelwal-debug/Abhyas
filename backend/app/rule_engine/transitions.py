"""Pedagogical act transition tables matching spec/04 §4.3."""

from backend.app.rule_engine.domain import ChildState, TeachingAct

ADVANCE: dict[TeachingAct, dict[ChildState, ChildState]] = {
    TeachingAct.ASK_TO_EXPLAIN: {
        ChildState.MISCONCEPTION: ChildState.CAN_EXPLAIN,
    },
    TeachingAct.CONCRETE_REPRESENTATION: {
        ChildState.MISCONCEPTION: ChildState.PARTIAL,
        ChildState.CAN_EXPLAIN: ChildState.PARTIAL,
    },
    TeachingAct.PROBE_SIMPLER_CASE: {
        ChildState.CAN_EXPLAIN: ChildState.PARTIAL,
    },
    TeachingAct.PHONICS_SOUND_OUT: {
        ChildState.MISCONCEPTION: ChildState.PARTIAL,
        ChildState.CAN_EXPLAIN: ChildState.PARTIAL,
    },
    TeachingAct.CONTRAST_TWO_ANSWERS: {
        ChildState.PARTIAL: ChildState.CORRECT,
    },
    TeachingAct.MODEL_STEP_ALOUD: {
        ChildState.PARTIAL: ChildState.CORRECT,
    },
    TeachingAct.INVOLVE_PEER: {
        ChildState.CAN_EXPLAIN: ChildState.PARTIAL,
    },
}

# Also support lookup by string value
for _act_enum, _trans_dict in list(ADVANCE.items()):
    ADVANCE[_act_enum.value] = _trans_dict  # type: ignore[index]


NON_ADVANCING: set[TeachingAct] = {
    TeachingAct.TELL_ANSWER,
    TeachingAct.REPEAT_QUESTION,
    TeachingAct.PRAISE_EFFORT,
    TeachingAct.PRAISE_GENERIC,
    TeachingAct.SCOLD,
    TeachingAct.OFF_TASK,
    TeachingAct.GIVE_NEW_PROBLEM,
}
