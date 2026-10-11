"""Domain models and types strictly matching spec/04 §4.1 and §4.3."""

from enum import IntEnum, StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field

from backend.app.content_models import (
    KeyPoint,
    ModuleRef,
    MoveCard,
    PersonaCard,
    Rubric,
    RubricCriterion,
    Scenario,
)


class Domain(StrEnum):
    """Domain of teaching move (§4.1)."""

    NUMERACY = "numeracy"
    LITERACY = "literacy"


class TeachingAct(StrEnum):
    """Fixed taxonomy for tagging teacher turns with 14 values (§4.3, §5.4)."""

    ASK_TO_EXPLAIN = "ask_to_explain"
    CONCRETE_REPRESENTATION = "concrete_representation"
    PROBE_SIMPLER_CASE = "probe_simpler_case"
    CONTRAST_TWO_ANSWERS = "contrast_answers"
    MODEL_STEP_ALOUD = "model_step_aloud"
    TELL_ANSWER = "tell_answer"
    REPEAT_QUESTION = "repeat_question"
    PRAISE_EFFORT = "praise_effort"
    PRAISE_GENERIC = "praise_generic"
    SCOLD = "scold"
    INVOLVE_PEER = "involve_peer"
    PHONICS_SOUND_OUT = "phonics_sound_out"
    OFF_TASK = "off_task"
    GIVE_NEW_PROBLEM = "give_new_problem"


class Problem(BaseModel):
    """An item the children work on (§4.1)."""

    type: Literal["sub", "add", "place_value", "read_word"]
    a: int | None = None  # sub/add: a − b or a + b (two-digit)
    b: int | None = None
    tens: int | None = None  # place_value: bundles of 10
    ones: int | None = None  #              loose sticks
    word: str | None = None  # read_word (Devanagari, NFC)

    def key(self) -> str:
        """Stable id e.g. 'sub:52-17', 'pv:4-7', 'word:मेला'."""
        if self.type in ("sub", "add"):
            op = "-" if self.type == "sub" else "+"
            return f"{self.type}:{self.a}{op}{self.b}"
        if self.type == "place_value":
            return f"pv:{self.tens}-{self.ones}"
        return f"word:{self.word}"


class Step(BaseModel):
    """One reasoning step, engine-rendered (§4.1)."""

    code: str  # e.g. "SUB_CANNOT", "SUB_SWAP", "REGROUP_OPEN_BUNDLE"
    nums: list[int] = Field(default_factory=list)  # every number mentioned in this step
    words: list[str] = Field(default_factory=list)  # every Hindi word token that must appear
    text_hi: str  # rendered template (digits as Arabic numerals)


class BugOutput(BaseModel):
    """Output produced by a procedural bug rule (§4.1)."""

    rule_id: str
    answer: int | str
    steps: list[Step] = Field(default_factory=list)


class ChildState(IntEnum):
    """State of child's internal procedural understanding (§4.1)."""

    MISCONCEPTION = 0  # applies bug, confident, no explanation
    CAN_EXPLAIN = 1  # still wrong, explains steps (reveals the bug)
    PARTIAL = 2  # correct with scaffold on current item; may relapse
    CORRECT = 3  # correct and explains why, on any item


class ChildRuntime(BaseModel):
    """Runtime state of one simulated child in the scene (§4.1)."""

    persona_id: str
    misconception: str  # bug rule id assigned by scenario
    temperament: Literal["confident", "shy", "distracted"]
    state: ChildState = ChildState.MISCONCEPTION
    partial_item_key: str | None = None  # item on which PARTIAL was reached
    silent_turns: int = 0
    turns_since_addressed: int = 0
    last_answer: int | str | None = None
    history: list[tuple[int, ChildState]] = Field(default_factory=list)


class SceneState(BaseModel):
    """State of an ongoing interactive rehearsal scene (§4.1)."""

    move_id: str
    domain: Domain
    effective_acts: list[str]  # from move.teaching_acts_effective
    target_causes: list[str]
    items: list[Problem]  # scenario items in order
    item_idx: int = 0
    current_item: Problem
    children: list[ChildRuntime]  # exactly 3 in normal mode, 1 in placement
    teacher_turns: int = 0
    last_responder: str | None = None
    ended: bool = False
    end_reason: str | None = None


class TaggedTurn(BaseModel):
    """Tagged teacher turn from act_tagger (§4.1)."""

    acts: list[TeachingAct]
    addressed_child: str | None = None  # persona id | "all" | None
    problem: Problem | None = None  # if teacher posed a new item


class ResponseKind(StrEnum):
    """Kind of child response produced by rule engine (§4.1)."""

    ANSWER = "answer"
    EXPLAIN_BUG = "explain_bug"
    SCAFFOLDED_CORRECT = "scaffolded_correct"
    RELAPSE = "relapse"
    CORRECT_EXPLAINED = "correct_explained"
    PARROT = "parrot"
    SILENT = "silent"
    OFF_TOPIC = "off_topic"
    INTERJECT = "interject"
    CONFUSED = "confused"


class ChildResponse(BaseModel):
    """Engine-computed response payload for one child (§4.1)."""

    persona_id: str
    kind: ResponseKind
    answer: int | str | None = None
    correct_answer: int | str | None = None
    steps: list[Step] = Field(default_factory=list)
    prior_state: ChildState
    new_state: ChildState
    affect: Literal["neutral", "confident", "encouraged", "upset", "shy", "distracted"]
    item: Problem
    allowed_numbers: set[int] = Field(default_factory=set)
    allowed_words: set[str] = Field(default_factory=set)
    forbidden: set[str] = Field(default_factory=set)


class StepResult(BaseModel):
    """Result of advancing the rule engine by one turn (§4.1)."""

    responses: list[ChildResponse]  # 1 main + at most 1 INTERJECT
    ended: bool = False
    end_reason: Literal["all_correct", "turn_limit", "teacher_stop"] | None = None


# Canonical aliases exported for rule engine and consumers
Move = MoveCard
Criterion = RubricCriterion
SourceRef = ModuleRef


class Persona(PersonaCard):
    """Runtime / legacy persona model extending PersonaCard."""

    model_config = {"extra": "allow"}
    name_hi: str = ""
    age: int = 7
    name: str | None = None
    grade: int | None = None
    misconceptions: list[str] = Field(default_factory=list)


class ScenarioItem(BaseModel):
    question: str
    expected_correct: Any = None
    context_notes: str | None = None


class ScriptLine(BaseModel):
    speaker: str
    text_hi: str
    act: str | None = None


__all__ = [
    "Domain",
    "TeachingAct",
    "Problem",
    "Step",
    "BugOutput",
    "ChildState",
    "ChildRuntime",
    "SceneState",
    "TaggedTurn",
    "ResponseKind",
    "ChildResponse",
    "StepResult",
    "KeyPoint",
    "ModuleRef",
    "MoveCard",
    "PersonaCard",
    "Rubric",
    "RubricCriterion",
    "Scenario",
    "Move",
    "Persona",
    "Criterion",
    "SourceRef",
    "ScenarioItem",
    "ScriptLine",
]
