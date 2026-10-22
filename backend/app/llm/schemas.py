"""Pydantic schemas for structured Claude outputs across every role in spec/05."""

from typing import Literal

from pydantic import BaseModel, Field

from backend.app.rule_engine.domain import Problem, TeachingAct
from backend.app.rule_engine.domain import SceneTurn as SceneTurn


# ── 5.3 Intent Router ────────────────────────────────────────────────────────
class IntentRouterOutput(BaseModel):
    """Output schema for intent_router role (spec/05 §5.3)."""

    intent: Literal[
        "answer_for_step",
        "question",
        "command_next",
        "command_skip",
        "command_repeat",
        "command_help",
        "smalltalk",
        "unclear",
    ]
    confidence: float = Field(ge=0.0, le=1.0)


# ── 5.4 Act Tagger ───────────────────────────────────────────────────────────
class ActTaggerOutput(BaseModel):
    """Output schema for act_tagger role (spec/05 §5.4)."""

    acts: list[TeachingAct]
    addressed_child: str | None = None  # persona id | "all" | None
    problem: Problem | None = None  # if teacher poses a new item
    quote: str = ""  # exact substring of transcript showing main act


# ── 5.5 Child Voice ──────────────────────────────────────────────────────────
class ChildVoiceOutput(BaseModel):
    """Output schema for child_voice role (spec/05 §5.5)."""

    line_hi: str


# ── 5.6 Coach ────────────────────────────────────────────────────────────────
class CoachFeedbackOutput(BaseModel):
    """Output schema for coach role (spec/05 §5.6)."""

    scores: dict[str, int]  # criterion_id -> 0 | 1 | 2
    evidence: dict[str, str]  # criterion_id -> exact teacher quote
    strength_hi: str
    change_hi: str
    exact_words_hi: str
    improved_since_last: bool = False
    confidence: float = Field(ge=0.0, le=1.0)


class CoachResult(BaseModel):
    """Role result returned by coach_feedback, separating review metadata from LLM output."""

    feedback: CoachFeedbackOutput
    needs_review: bool
    review_reason: str | None = None
    used_fallback: bool = False


# ── 5.7 Fidelity Checker ─────────────────────────────────────────────────────
class KeyPointEvaluation(BaseModel):
    """Single key point evaluation item for fidelity_checker (spec/05 §5.7)."""

    id: str
    status: Literal["covered", "partial", "missing"]
    quote: str = ""


class FidelityCheckerOutput(BaseModel):
    """Output schema for fidelity_checker role (spec/05 §5.7)."""

    points: list[KeyPointEvaluation]
    misconceptions: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)


class FidelityResult(BaseModel):
    """Role result returned by check_fidelity, separating review metadata from LLM output."""

    output: FidelityCheckerOutput
    reply_hi: str
    needs_review: bool
    review_reason: str | None = None
    used_fallback: bool = False


# ── 5.8 Ask Any Time Roles ───────────────────────────────────────────────────
class QuestionClassifierOutput(BaseModel):
    """Output schema for question_classifier role (spec/05 §5.8)."""

    category: Literal["pedagogy", "classroom_management", "admin", "out_of_scope"]
    needs_clarification: bool = False
    clarifying_question_hi: str = ""
    search_query_hi: str = ""
    confidence: float = Field(ge=0.0, le=1.0)


QuestionClassificationOutput = QuestionClassifierOutput


class QuestionClassificationResult(BaseModel):
    """Runtime result returned by question_classifier role."""

    output: QuestionClassifierOutput
    guarded: bool = True
    guard_error: str | None = None
    used_fallback: bool = False


class RetrievedChunk(BaseModel):
    """Retrieved reference document chunk for guide_answerer (§5.8)."""

    chunk_id: str
    source_short_hi: str
    section: str = ""
    page: int | None = None
    text: str
    score: float | None = None


class GuideAnswererOutput(BaseModel):
    """Output schema for guide_answerer role (spec/05 §5.8)."""

    answer_hi: str
    source_ids: list[str] = Field(default_factory=list)
    try_this_week_hi: str = ""
    confidence: float = Field(ge=0.0, le=1.0)


GuideAnswerOutput = GuideAnswererOutput


class GuideAnswerResult(BaseModel):
    """Runtime result returned by guide_answerer role."""

    output: GuideAnswererOutput
    answer_text_hi: str
    escalated: bool = False
    sources_cited: list[RetrievedChunk] = Field(default_factory=list)
    guarded: bool = True
    guard_error: str | None = None
    used_fallback: bool = False
    no_sources: bool = False  # escalated because the excerpts did not support an answer


# ── 5.9 Build-Time Roles ─────────────────────────────────────────────────────
class MoveReviewIssue(BaseModel):
    """Single issue found during move review (spec/05 §5.9)."""

    field: str
    severity: Literal["error", "warning", "info"]
    note_hi: str


class MoveReviewerOutput(BaseModel):
    """Output schema for move_reviewer role (spec/05 §5.9)."""

    issues: list[MoveReviewIssue] = Field(default_factory=list)
    approve_recommendation: bool = False


class ModelTeacherLine(BaseModel):
    """One teacher line in model rehearsal script (spec/05 §5.9)."""

    teacher_line_hi: str
    act_id: TeachingAct


class ModelTeacherOutput(BaseModel):
    """Output schema for model_teacher role (spec/05 §5.9)."""

    lines: list[ModelTeacherLine] = Field(default_factory=list)


class PageOCROutput(BaseModel):
    """Output schema for page_ocr role (spec/05 §5.9)."""

    text_hi: str
