"""Pydantic content models and schema exporters (spec/10 §10.2, §10.6)."""

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


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
    # English mirror, shown when the UI language is English (required in one-on-one banks)
    strength_en: str = ""
    change_en: str = ""
    exact_words_en: str = ""


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


# The one-on-one rubric: the teacher talks to a single child ("involve all children" is dropped).
ONE_ON_ONE_CRITERIA: tuple[str, ...] = (
    "asks_to_explain",
    "does_not_tell_answer",
    "uses_concrete_representation",
    "probes_with_followup",
    "checks_on_new_problem",
)


class MisconceptionContent(BaseModel):
    """One scenario misconception as the diagnosis step sees it (Hindi / Hinglish / English)."""

    label_hi: str
    label_en: str
    reveal_hi: str  # {child} placeholder; shown after the teacher's diagnosis
    reveal_en: str
    keywords: list[str] = Field(min_length=1)  # any one is a hit; matched on NFC-lowercased text


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
    # One-on-one practice (spec: rehearsal with a single child, diagnose first)
    rubric_one_on_one: Rubric | None = None
    feedback_bank_one_on_one: dict[str, FeedbackItem] = Field(default_factory=dict)
    misconceptions: dict[str, MisconceptionContent] = Field(default_factory=dict)
    diagnosis_topic_keywords: list[str] = Field(default_factory=list)
    one_on_one_intro_hi: str = ""
    one_on_one_intro_en: str = ""

    @model_validator(mode="after")
    def _validate_one_on_one(self) -> "MoveCard":
        if self.rubric_one_on_one is None:
            if self.domain == Domain.NUMERACY:
                raise ValueError("numeracy move cards need a rubric_one_on_one")
            return self
        ids = [c.id for c in self.rubric_one_on_one.criteria]
        if sorted(ids) != sorted(ONE_ON_ONE_CRITERIA):
            raise ValueError(f"rubric_one_on_one criteria must be {ONE_ON_ONE_CRITERIA}, got {ids}")
        for crit in self.rubric_one_on_one.criteria:
            if sorted(crit.levels) != [0, 1, 2]:
                raise ValueError(f"rubric_one_on_one criterion {crit.id} needs levels 0, 1 and 2")
        if sorted(self.feedback_bank_one_on_one) != sorted(ONE_ON_ONE_CRITERIA):
            raise ValueError(
                "feedback_bank_one_on_one must have one entry per one-on-one criterion"
            )
        for crit_id, item in self.feedback_bank_one_on_one.items():
            for field in (
                "strength_hi",
                "change_hi",
                "exact_words_hi",
                "strength_en",
                "change_en",
                "exact_words_en",
            ):
                if not getattr(item, field).strip():
                    raise ValueError(f"feedback_bank_one_on_one.{crit_id}.{field} is empty")
        if not self.diagnosis_topic_keywords:
            raise ValueError("diagnosis_topic_keywords must not be empty")
        if "{child}" not in self.one_on_one_intro_hi or "{child}" not in self.one_on_one_intro_en:
            raise ValueError("one_on_one_intro_hi/en must contain {child}")
        return self

    def one_on_one_view(self) -> "MoveCard":
        """A copy whose rubric and feedback bank are the one-on-one ones (coach input)."""
        if self.rubric_one_on_one is None:
            return self
        return self.model_copy(
            update={
                "rubric": self.rubric_one_on_one,
                "feedback_bank": dict(self.feedback_bank_one_on_one),
            }
        )


class PersonaCard(BaseModel):
    id: str
    name_hi: str
    age: int
    temperament: Literal["confident", "shy", "distracted"]
    voice_id: str
    speech_style_hi: str
    off_topic_lines_hi: list[str] = Field(default_factory=list)
