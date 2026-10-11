"""Domain models strictly matching Section 3 of ARCHITECTURE.md."""

from enum import Enum
from typing import Any, Literal, Optional
from pydantic import BaseModel, Field


class TeachingAct(str, Enum):
    """Fixed taxonomy for tagging teacher turns (§3)."""
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


class SourceRef(BaseModel):
    module_name: str
    section: str
    page: Optional[int] = None


class KeyPoint(BaseModel):
    id: str
    text_hi: str
    must_have: bool = True


class Criterion(BaseModel):
    id: str
    text: str
    levels: dict[int, str]  # 0, 1, 2 descriptors


class Rubric(BaseModel):
    criteria: list[Criterion]


class ScriptLine(BaseModel):
    speaker: str
    text_hi: str
    act: Optional[str] = None


class Persona(BaseModel):
    """An AI child persona representation (§3)."""
    id: str
    name: str
    grade: int
    voice_id: str
    misconceptions: list[str]  # e.g. ["SUB_SMALLER_FROM_LARGER"]
    temperament: Literal["shy", "confident", "distracted"]
    speech_style_hi: str


class ScenarioItem(BaseModel):
    question: str
    expected_correct: Any
    context_notes: Optional[str] = None


class Scenario(BaseModel):
    problem_text_hi: str
    items: list[ScenarioItem] = Field(default_factory=list)
    personas: list[Persona] = Field(default_factory=list)


class Move(BaseModel):
    """One teachable practice card (§3)."""
    id: str
    domain: Literal["numeracy", "literacy"]
    title_hi: str
    module_ref: SourceRef
    sankul_month: Optional[str] = None
    key_points: list[KeyPoint]
    teaching_acts_effective: list[str]
    target_causes: list[str]
    rubric: Rubric
    learn_script_hi: str
    model_rehearsal: list[ScriptLine]
    scenario: Scenario
    peer_checklist: list[str]
    reflection_questions: list[str]
