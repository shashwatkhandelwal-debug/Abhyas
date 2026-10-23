"""SQLAlchemy 2.0 models strictly matching spec/03_data_model.md §3.2."""

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    PrimaryKeyConstraint,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, BYTEA, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base

# Vector type handling: support pgvector when installed, fallback to JSONB/ARRAY for mocks
try:
    from pgvector.sqlalchemy import Vector

    VECTOR_1024 = Vector(1024)
except ImportError:
    VECTOR_1024 = JSONB  # type: ignore


# ── Organisation ─────────────────────────────────────────────────────────


class Batch(Base):
    __tablename__ = "batch"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    district: Mapped[str | None] = mapped_column(Text, nullable=True)
    block_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    module: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )


class Cluster(Base):
    __tablename__ = "cluster"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    block_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    district: Mapped[str | None] = mapped_column(Text, nullable=True)


class AppUser(Base):
    __tablename__ = "app_user"
    __table_args__ = (
        CheckConstraint(
            "role IN ('teacher', 'arp', 'trainer', 'coach', 'admin')",
            name="check_app_user_role",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    cluster_id: Mapped[str | None] = mapped_column(Text, ForeignKey("cluster.id"), nullable=True)
    district: Mapped[str | None] = mapped_column(Text, nullable=True)
    teacher_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # UI language: 'hi' (default) or 'en'. Nullable so rows created before the column keep working.
    ui_lang: Mapped[str | None] = mapped_column(
        Text, nullable=True, default="hi", server_default="hi"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )

    @property
    def is_demo_account(self) -> bool:
        return bool(self.is_demo)


class Teacher(Base):
    __tablename__ = "teacher"
    __table_args__ = (
        CheckConstraint(
            "experience_band IN ('0-1', '2-5', '6-10', '10+') OR experience_band IS NULL",
            name="check_teacher_experience_band",
        ),
        CheckConstraint(
            "address_form IN ('f', 'm')",
            name="check_teacher_address_form",
        ),
        CheckConstraint(
            "preferred_channel IN ('whatsapp', 'web')",
            name="check_teacher_preferred_channel",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    phone_hash: Mapped[str | None] = mapped_column(Text, unique=True, nullable=True)
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    school_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    cluster_id: Mapped[str | None] = mapped_column(Text, ForeignKey("cluster.id"), nullable=True)
    block_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    district: Mapped[str | None] = mapped_column(Text, nullable=True)
    batch_id: Mapped[str | None] = mapped_column(Text, ForeignKey("batch.id"), nullable=True)
    experience_band: Mapped[str | None] = mapped_column(Text, nullable=True)
    first_year: Mapped[bool | None] = mapped_column(Boolean, default=False)
    classes: Mapped[list[int] | None] = mapped_column(ARRAY(Integer), nullable=True)
    address_form: Mapped[str] = mapped_column(Text, default="f", nullable=False)
    preferred_channel: Mapped[str] = mapped_column(Text, default="whatsapp", nullable=False)
    lite_mode: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    consent_service: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    consent_share_scores: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    consent_class_audio: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    consent_research: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    onboarding_state: Mapped[str] = mapped_column(Text, default="NEW", nullable=False)
    # "My class": ids from content/class_struggles.yaml, ordered, at most STRUGGLE_MAX_CHOSEN
    class_struggles: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    # "What do you want to get better at?": ids from content/teaching_skills.yaml, at most 2
    teaching_skills: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    class_profile_prompted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_inbound_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )

    @property
    def is_demo_account(self) -> bool:
        return bool(self.is_demo)


class TeacherContact(Base):
    __tablename__ = "teacher_contact"

    teacher_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("teacher.id", ondelete="CASCADE"),
        primary_key=True,
    )
    phone_enc: Mapped[bytes] = mapped_column(BYTEA, nullable=False)


class InviteCode(Base):
    __tablename__ = "invite_code"

    code: Mapped[str] = mapped_column(Text, primary_key=True)
    cluster_id: Mapped[str | None] = mapped_column(Text, ForeignKey("cluster.id"), nullable=True)
    batch_id: Mapped[str | None] = mapped_column(Text, ForeignKey("batch.id"), nullable=True)
    district: Mapped[str | None] = mapped_column(Text, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class ARPAssignment(Base):
    __tablename__ = "arp_assignment"
    __table_args__ = (PrimaryKeyConstraint("arp_user_id", "cluster_id"),)

    arp_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app_user.id"), nullable=False
    )
    cluster_id: Mapped[str] = mapped_column(Text, ForeignKey("cluster.id"), nullable=False)


class ConsentLog(Base):
    __tablename__ = "consent_log"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    teacher_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("teacher.id"), nullable=True
    )
    field: Mapped[str] = mapped_column(Text, nullable=False)
    value: Mapped[bool] = mapped_column(Boolean, nullable=False)
    channel: Mapped[str | None] = mapped_column(Text, nullable=True)
    text_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )


# ── Content (published releases) ─────────────────────────────────────────


class ContentRelease(Base):
    __tablename__ = "content_release"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    published_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app_user.id"), nullable=True
    )
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class Move(Base):
    __tablename__ = "move"
    __table_args__ = (
        PrimaryKeyConstraint("id", "release_id"),
        CheckConstraint(
            "status IN ('draft', 'in_review', 'approved')",
            name="check_move_status",
        ),
    )

    id: Mapped[str] = mapped_column(Text, nullable=False)
    release_id: Mapped[str] = mapped_column(Text, ForeignKey("content_release.id"), nullable=False)
    domain: Mapped[str] = mapped_column(Text, nullable=False)
    title_hi: Mapped[str] = mapped_column(Text, nullable=False)
    sankul_month: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    approvals: Mapped[list[Any]] = mapped_column(JSONB, default=list, nullable=False)


class Persona(Base):
    __tablename__ = "persona"
    __table_args__ = (PrimaryKeyConstraint("id", "release_id"),)

    id: Mapped[str] = mapped_column(Text, nullable=False)
    release_id: Mapped[str] = mapped_column(Text, ForeignKey("content_release.id"), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)


class BugRule(Base):
    __tablename__ = "bug_rule"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('math', 'reading')",
            name="check_bug_rule_kind",
        ),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    kind: Mapped[str | None] = mapped_column(Text, nullable=True)
    code_ref: Mapped[str] = mapped_column(Text, nullable=False)
    description_hi: Mapped[str | None] = mapped_column(Text, nullable=True)
    research_ref: Mapped[str | None] = mapped_column(Text, nullable=True)


# ── Sessions ─────────────────────────────────────────────────────────────


class SessionState(Base):
    __tablename__ = "session_state"
    __table_args__ = (PrimaryKeyConstraint("teacher_id", "week_start"),)

    teacher_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("teacher.id", ondelete="CASCADE"),
        nullable=False,
    )
    week_start: Mapped[date] = mapped_column(Date, nullable=False)
    move_id: Mapped[str] = mapped_column(Text, nullable=False)
    state: Mapped[str] = mapped_column(Text, nullable=False)
    prior_state: Mapped[str | None] = mapped_column(Text, nullable=True)
    rehearse_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    context: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )


class MovePath(Base):
    __tablename__ = "move_path"
    __table_args__ = (PrimaryKeyConstraint("teacher_id", "position"),)

    teacher_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("teacher.id", ondelete="CASCADE"),
        nullable=False,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    move_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class Scene(Base):
    __tablename__ = "scene"
    __table_args__ = (
        CheckConstraint(
            "mode IN ('normal', 'placement', 'sankul')",
            name="check_scene_mode",
        ),
        CheckConstraint(
            "status IN ('active', 'ended')",
            name="check_scene_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    teacher_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("teacher.id", ondelete="CASCADE"),
        nullable=False,
    )
    move_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    week_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    attempt: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mode: Mapped[str] = mapped_column(Text, default="normal", nullable=False)
    engine_state: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(Text, default="active", nullable=False)
    end_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    teacher_turns: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Turn(Base):
    __tablename__ = "turn"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    teacher_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("teacher.id", ondelete="CASCADE"),
        nullable=False,
    )
    scene_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("scene.id", ondelete="CASCADE"),
        nullable=False,
    )
    idx: Mapped[int | None] = mapped_column(Integer, nullable=True)
    role: Mapped[str] = mapped_column(Text, nullable=False)
    transcript: Mapped[str | None] = mapped_column(Text, nullable=True)
    stt_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    acts: Mapped[list[str] | None] = mapped_column(ARRAY(Text), nullable=True)
    addressed_child: Mapped[str | None] = mapped_column(Text, nullable=True)
    problem: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    rule_result: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    line_hi: Mapped[str | None] = mapped_column(Text, nullable=True)
    guard_status: Mapped[str | None] = mapped_column(Text, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stage_ms: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )


class MessageTranslation(Base):
    """Cached on-demand translation of a bubble, keyed by (message, target language)."""

    __tablename__ = "message_translation"

    message_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("message.id", ondelete="CASCADE"), primary_key=True
    )
    lang: Mapped[str] = mapped_column(Text, primary_key=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )


class Message(Base):
    __tablename__ = "message"
    __table_args__ = (
        CheckConstraint(
            "direction IN ('in', 'out')",
            name="check_message_direction",
        ),
        UniqueConstraint("channel", "channel_msg_id", name="uq_channel_channel_msg_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    teacher_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("teacher.id", ondelete="CASCADE"),
        nullable=False,
    )
    direction: Mapped[str] = mapped_column(Text, nullable=False)
    channel: Mapped[str] = mapped_column(Text, nullable=False)
    channel_msg_id: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str | None] = mapped_column(Text, nullable=True)
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    audio_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    buttons: Mapped[list[Any] | None] = mapped_column(JSONB, nullable=True)
    citations: Mapped[list[Any] | None] = mapped_column(JSONB, nullable=True)
    speaker: Mapped[str | None] = mapped_column(Text, nullable=True)
    template_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    state_at: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )


# ── Scores & Evidence ────────────────────────────────────────────────────


class RehearsalScore(Base):
    __tablename__ = "rehearsal_score"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    teacher_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("teacher.id", ondelete="CASCADE"),
        nullable=False,
    )
    scene_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("scene.id"), nullable=True
    )
    move_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempt: Mapped[int | None] = mapped_column(Integer, nullable=True)
    scores: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    strength_hi: Mapped[str | None] = mapped_column(Text, nullable=True)
    change_hi: Mapped[str | None] = mapped_column(Text, nullable=True)
    exact_words_hi: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    prompt_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    model: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )


class ExplainScore(Base):
    __tablename__ = "explain_score"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    teacher_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("teacher.id", ondelete="CASCADE"),
        nullable=False,
    )
    move_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    transcript: Mapped[str | None] = mapped_column(Text, nullable=True)
    points: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    misconceptions: Mapped[list[str] | None] = mapped_column(ARRAY(Text), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    prompt_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    model: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )


class AdoptionEvidence(Base):
    __tablename__ = "adoption_evidence"
    __table_args__ = (
        CheckConstraint(
            "level BETWEEN 1 AND 5",
            name="check_adoption_evidence_level",
        ),
        CheckConstraint(
            "source IN ('rehearsal', 'reflection', 'peer_checklist', 'arp_observation', 'child_check')",
            name="check_adoption_evidence_source",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    teacher_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("teacher.id", ondelete="CASCADE"),
        nullable=False,
    )
    move_id: Mapped[str] = mapped_column(Text, nullable=False)
    level: Mapped[int] = mapped_column(Integer, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    detail: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )


class ClassOutcome(Base):
    """The teacher's own answer to "Did it help your class?" after trying a move in class."""

    __tablename__ = "class_outcome"
    __table_args__ = (
        CheckConstraint("answer IN ('yes', 'some', 'no')", name="check_class_outcome_answer"),
        Index("idx_class_outcome_teacher", "teacher_id", "move_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    teacher_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("teacher.id", ondelete="CASCADE"),
        nullable=False,
    )
    move_id: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    struggle_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )


class RealismRating(Base):
    __tablename__ = "realism_rating"
    __table_args__ = (
        CheckConstraint(
            "rating BETWEEN 1 AND 5",
            name="check_realism_rating_range",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    teacher_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("teacher.id", ondelete="CASCADE"),
        nullable=False,
    )
    scene_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("scene.id"), nullable=True
    )
    rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )


class ModuleProgress(Base):
    """One teacher's progress through one module: learn, diagnose a child (1-1), practise, check."""

    __tablename__ = "module_progress"
    __table_args__ = (
        CheckConstraint(
            "diagnose_verdict IS NULL OR diagnose_verdict IN ('correct', 'partly', 'wrong', 'skipped')",
            name="check_module_progress_verdict",
        ),
    )

    teacher_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("teacher.id", ondelete="CASCADE"),
        primary_key=True,
    )
    module_id: Mapped[str] = mapped_column(Text, primary_key=True)  # the move id
    learn_done_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    diagnose_done_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    diagnose_verdict: Mapped[str | None] = mapped_column(Text, nullable=True)
    practise_done_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    check_done_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    check_passed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    check_covered: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )


class TrainingRating(Base):
    """End-of-week "rate the training" feedback: 1-5 usefulness plus an optional one-line comment."""

    __tablename__ = "training_rating"
    __table_args__ = (
        CheckConstraint(
            "rating BETWEEN 1 AND 5",
            name="check_training_rating_range",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    teacher_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("teacher.id", ondelete="CASCADE"),
        nullable=False,
    )
    move_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )


# ── Ask Any Time ─────────────────────────────────────────────────────────


class Question(Base):
    __tablename__ = "question"
    __table_args__ = (
        CheckConstraint(
            "status IN ('answered', 'escalated', 'arp_answered', 'closed')",
            name="check_question_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    teacher_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("teacher.id", ondelete="CASCADE"),
        nullable=False,
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str | None] = mapped_column(Text, nullable=True)
    clarifying_asked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    answer_hi: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_ids: Mapped[list[str] | None] = mapped_column(ARRAY(Text), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    followup_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    followup_result: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )


class DocChunk(Base):
    __tablename__ = "doc_chunk"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    source_id: Mapped[str] = mapped_column(Text, nullable=False)
    source_short_hi: Mapped[str | None] = mapped_column(Text, nullable=True)
    section: Mapped[str | None] = mapped_column(Text, nullable=True)
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    tokens: Mapped[list[str] | None] = mapped_column(ARRAY(Text), nullable=True)
    embedding: Mapped[Any] = mapped_column(VECTOR_1024, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )


# ── Review / Ops ─────────────────────────────────────────────────────────


class ReviewItem(Base):
    __tablename__ = "review_item"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('rehearsal_score', 'explain_score', 'question', 'move', 'guard_failure')",
            name="check_review_item_kind",
        ),
        CheckConstraint(
            "status IN ('open', 'resolved')",
            name="check_review_item_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    kind: Mapped[str | None] = mapped_column(Text, nullable=True)
    ref_id: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, default="open", nullable=False)
    resolution: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CalibrationLabel(Base):
    __tablename__ = "calibration_label"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scene_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("scene.id"), nullable=True
    )
    explain_score_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("explain_score.id"), nullable=True
    )
    coach_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app_user.id"), nullable=True
    )
    scores: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    blind: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )


class ARPObservation(Base):
    __tablename__ = "arp_observation"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    arp_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app_user.id"), nullable=True
    )
    teacher_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("teacher.id", ondelete="CASCADE"),
        nullable=False,
    )
    move_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    checklist: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    observed_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )


class ScheduledJob(Base):
    __tablename__ = "scheduled_job"
    __table_args__ = (
        Index("ix_scheduled_job_status_run_at", "status", "run_at"),
        CheckConstraint(
            "status IN ('pending', 'done', 'failed', 'cancelled')",
            name="check_scheduled_job_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(Text, default="pending", nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )


class TemplateSend(Base):
    __tablename__ = "template_send"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    teacher_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    template_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str | None] = mapped_column(Text, nullable=True)
    est_cost_inr: Mapped[float | None] = mapped_column(Numeric(8, 3), nullable=True)
    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )


class LLMCall(Base):
    __tablename__ = "llm_call"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    role: Mapped[str | None] = mapped_column(Text, nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    model: Mapped[str | None] = mapped_column(Text, nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cache_read_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    outcome: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )


class SpeechSpend(Base):
    __tablename__ = "speech_spend"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('stt', 'tts')",
            name="check_speech_spend_kind",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    units: Mapped[int] = mapped_column(Integer, nullable=False)
    cost_inr: Mapped[float] = mapped_column(Float, nullable=False)


class TTSAudio(Base):
    __tablename__ = "tts_audio"

    cache_key: Mapped[str] = mapped_column(Text, primary_key=True)
    ogg: Mapped[bytes | None] = mapped_column(BYTEA, nullable=True)
    mp3: Mapped[bytes | None] = mapped_column(BYTEA, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )


# ── Aggregates for Trainer View ──────────────────────────────────────────


class AggModuleBatch(Base):
    __tablename__ = "agg_module_batch"
    __table_args__ = (PrimaryKeyConstraint("batch_id", "move_id"),)

    batch_id: Mapped[str] = mapped_column(Text, nullable=False)
    move_id: Mapped[str] = mapped_column(Text, nullable=False)
    n_teachers: Mapped[int | None] = mapped_column(Integer, nullable=True)
    explain_missing: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    rubric_dist: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    ladder_dist: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    active_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
