"""Pydantic schemas for structured Claude outputs across all five roles (§9)."""

from typing import Any, Literal

from pydantic import BaseModel, Field

from backend.app.rule_engine.domain import TeachingAct


class ActTaggerOutput(BaseModel):
    """Output schema for the act_tagger role."""

    acts: list[TeachingAct]
    addressed_child: str | None = None
    quote: str


class ChildVoiceOutput(BaseModel):
    """Output schema for the child_voice role."""

    line_hi: str
    numbers_cited: list[Any] = Field(default_factory=list)


class CoachFeedbackOutput(BaseModel):
    """Output schema for the coach role (§5.3)."""

    scores: dict[str, int]  # criterion_id -> 0 | 1 | 2
    evidence: dict[str, str]  # criterion_id -> exact teacher quote
    strength_hi: str
    change_hi: str
    exact_words_hi: str
    confidence: float = Field(ge=0.0, le=1.0)


class KeyPointEvaluation(BaseModel):
    id: str
    status: Literal["covered", "partial", "missing"]
    quote: str | None = None


class FidelityCheckerOutput(BaseModel):
    """Output schema for the fidelity_checker role (§6)."""

    points: list[KeyPointEvaluation]
    misconceptions: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)


class GuideAnswererOutput(BaseModel):
    """Output schema for the guide_answerer role (§8)."""

    answer_hi: str
    source_ids: list[str]
    confidence: float = Field(ge=0.0, le=1.0)
