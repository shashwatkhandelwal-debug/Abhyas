"""SQLAlchemy 2.0 models strictly matching Section 12 data model."""

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    PrimaryKeyConstraint,
    Text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base

# Note: pgvector Vector type when available, fallback to ARRAY/JSONB if running in non-pgvector test env
try:
    from pgvector.sqlalchemy import Vector

    VECTOR_TYPE = Vector(1024)
except ImportError:
    VECTOR_TYPE = JSONB  # type: ignore


class Teacher(Base):
    __tablename__ = "teacher"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    phone_hash: Mapped[str] = mapped_column(Text, unique=True, index=True, nullable=False)
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    school_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    cluster_id: Mapped[str | None] = mapped_column(Text, index=True, nullable=True)
    block_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    district: Mapped[str | None] = mapped_column(Text, nullable=True)
    batch_id: Mapped[str | None] = mapped_column(Text, index=True, nullable=True)
    experience_band: Mapped[str | None] = mapped_column(Text, nullable=True)
    first_year: Mapped[bool | None] = mapped_column(Boolean, default=False)
    classes: Mapped[list[int] | None] = mapped_column(ARRAY(Integer), default=list)
    consent_share_scores: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    consent_class_audio: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )


class ARP(Base):
    __tablename__ = "arp"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    cluster_id: Mapped[str] = mapped_column(Text, index=True, nullable=False)
    phone_hash: Mapped[str] = mapped_column(Text, unique=True, nullable=False)


class Move(Base):
    __tablename__ = "move"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    version: Mapped[str] = mapped_column(Text, nullable=False)
    domain: Mapped[str] = mapped_column(Text, nullable=False)  # numeracy | literacy
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    sankul_month: Mapped[str | None] = mapped_column(Text, nullable=True)


class Persona(Base):
    __tablename__ = "persona"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    version: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)


class Rule(Base):
    __tablename__ = "rule"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    version: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)  # math | reading
    code_ref: Mapped[str] = mapped_column(Text, nullable=False)


class SessionState(Base):
    __tablename__ = "session_state"
    __table_args__ = (PrimaryKeyConstraint("teacher_id", "week"),)

    teacher_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("teacher.id"), nullable=False
    )
    week: Mapped[date] = mapped_column(Date, nullable=False)
    move_id: Mapped[str] = mapped_column(Text, nullable=False)
    state: Mapped[str] = mapped_column(Text, nullable=False)  # State machine enum
    retries: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_inbound_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    context: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)


class Turn(Base):
    __tablename__ = "turn"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    teacher_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("teacher.id"), nullable=False
    )
    week: Mapped[date] = mapped_column(Date, nullable=False)
    role: Mapped[str] = mapped_column(Text, nullable=False)
    transcript: Mapped[str] = mapped_column(Text, nullable=False)
    acts: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    child_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    rule_result: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )


class RehearsalScore(Base):
    __tablename__ = "rehearsal_score"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    teacher_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("teacher.id"), nullable=False
    )
    move_id: Mapped[str] = mapped_column(Text, nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False)
    scores: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )


class ExplainScore(Base):
    __tablename__ = "explain_score"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    teacher_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("teacher.id"), nullable=False
    )
    move_id: Mapped[str] = mapped_column(Text, nullable=False)
    points: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    misconceptions: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )


class AdoptionEvidence(Base):
    __tablename__ = "adoption_evidence"
    __table_args__ = (PrimaryKeyConstraint("teacher_id", "move_id", "created_at"),)

    teacher_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("teacher.id"), nullable=False
    )
    move_id: Mapped[str] = mapped_column(Text, nullable=False)
    level: Mapped[int] = mapped_column(Integer, nullable=False)  # 1 to 5
    source: Mapped[str] = mapped_column(Text, nullable=False)
    detail: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )


class Question(Base):
    __tablename__ = "question"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    teacher_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("teacher.id"), nullable=False
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_ids: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(
        Text, default="answered"
    )  # answered | escalated | pending_review
    followup_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DocChunk(Base):
    __tablename__ = "doc_chunk"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    section: Mapped[str] = mapped_column(Text, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[Any] = mapped_column(VECTOR_TYPE, nullable=True)


class ReviewItem(Base):
    __tablename__ = "review_item"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    kind: Mapped[str] = mapped_column(
        Text, nullable=False
    )  # question | rehearsal_score | explain_score
    ref_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, default="pending")  # pending | reviewed | resolved
