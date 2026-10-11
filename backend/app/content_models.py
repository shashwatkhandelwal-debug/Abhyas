"""Pydantic content models and schema exporters (spec/10 §10.2, §10.6)."""

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class Domain(StrEnum):
    NUMERACY = "numeracy"
    LITERACY = "literacy"


class MoveStatus(StrEnum):
    DRAFT = "draft"
    IN_REVIEW = "in_review"
    APPROVED = "approved"


class ModuleRef(BaseModel):
    source_id: str
    section: str
    page: int | None = None
    verified: bool = False


class KeyPoint(BaseModel):
    id: str
    text_hi: str
    must_have: bool = False
    keywords_hi: list[str] = Field(default_factory=list)
    source_chunk_ids: list[str] = Field(default_factory=list)

    @field_validator("keywords_hi", mode="before")
    @classmethod
    def coerce_keywords_to_str(cls, v: Any) -> list[str]:
        if isinstance(v, list):
            return [str(item) for item in v]
        return [str(v)] if v is not None else []


class RubricCriterion(BaseModel):
    id: str
    text_hi: str
    levels: dict[int, str]
    signal_acts: list[str] = Field(default_factory=list)
    negative_acts: list[str] = Field(default_factory=list)


class Rubric(BaseModel):
    criteria: list[RubricCriterion]


class FeedbackItem(BaseModel):
    strength_hi: str
    change_hi: str
    exact_words_hi: str


class ProblemItem(BaseModel):
    type: str
    a: int | None = None
    b: int | None = None
    word: str | None = None
    options: list[str] | None = None


class ScenarioChild(BaseModel):
    persona_id: str
    misconception: str


class Scenario(BaseModel):
    intro_hi: str
    items: list[dict[str, Any]]
    children: list[ScenarioChild]
    guess_lexicon: dict[str, list[str]] = Field(default_factory=dict)


class ModelRehearsalTurn(BaseModel):
    speaker: str
    text_hi: str
    acts: list[str] = Field(default_factory=list)
    addressed: str | None = None
    problem: dict[str, Any] | None = None


class MoveCard(BaseModel):
    id: str = Field(pattern=r"^[A-Z]{3}_[A-Z0-9_]+$")
    version: int = 1
    status: MoveStatus
    domain: Domain
    grade: list[int]
    title_hi: str
    summary_hi: str
    tags: list[str] = Field(default_factory=list)
    module_ref: ModuleRef
    sankul_month: str | None = None
    key_points: list[KeyPoint]
    teaching_acts_effective: list[str]
    target_causes: list[str]
    rubric: Rubric
    feedback_bank: dict[str, FeedbackItem]
    learn_script_hi: str
    learn_summary_hi: list[str]
    scenario: Scenario
    model_rehearsal: list[ModelRehearsalTurn]
    peer_checklist: list[str]
    reflection_questions: list[str]
    approvals: list[dict[str, Any]] = Field(default_factory=list)


class PersonaCard(BaseModel):
    id: str
    name_hi: str
    age: int
    temperament: Literal["confident", "shy", "distracted"]
    voice_id: str
    speech_style_hi: str
    off_topic_lines_hi: list[str] = Field(default_factory=list)
