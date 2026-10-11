"""Initial schema for all tables in spec/03_data_model.md.

Revision ID: 6a7a8609f2ce
Revises:
Create Date: 2026-10-11 15:47:20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "6a7a8609f2ce"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Extensions
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto;")

    # ── Organisation ─────────────────────────────────────────────────────────
    op.create_table(
        "batch",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("district", sa.Text(), nullable=True),
        sa.Column("block_id", sa.Text(), nullable=True),
        sa.Column("module", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    op.create_table(
        "cluster",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("block_id", sa.Text(), nullable=True),
        sa.Column("district", sa.Text(), nullable=True),
    )

    op.create_table(
        "app_user",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("username", sa.Text(), unique=True, nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=True),
        sa.Column("cluster_id", sa.Text(), sa.ForeignKey("cluster.id"), nullable=True),
        sa.Column("district", sa.Text(), nullable=True),
        sa.Column("teacher_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("is_demo", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "role IN ('teacher', 'arp', 'trainer', 'coach', 'admin')",
            name="check_app_user_role",
        ),
    )

    op.create_table(
        "teacher",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("phone_hash", sa.Text(), unique=True, nullable=True),
        sa.Column("name", sa.Text(), nullable=True),
        sa.Column("school_id", sa.Text(), nullable=True),
        sa.Column("cluster_id", sa.Text(), sa.ForeignKey("cluster.id"), nullable=True),
        sa.Column("block_id", sa.Text(), nullable=True),
        sa.Column("district", sa.Text(), nullable=True),
        sa.Column("batch_id", sa.Text(), sa.ForeignKey("batch.id"), nullable=True),
        sa.Column("experience_band", sa.Text(), nullable=True),
        sa.Column("first_year", sa.Boolean(), server_default=sa.text("false"), nullable=True),
        sa.Column("classes", postgresql.ARRAY(sa.Integer()), nullable=True),
        sa.Column("address_form", sa.Text(), server_default=sa.text("'f'"), nullable=False),
        sa.Column(
            "preferred_channel", sa.Text(), server_default=sa.text("'whatsapp'"), nullable=False
        ),
        sa.Column("lite_mode", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("consent_service", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "consent_share_scores", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column(
            "consent_class_audio", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column(
            "consent_research", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("is_demo", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("onboarding_state", sa.Text(), server_default=sa.text("'NEW'"), nullable=False),
        sa.Column("last_inbound_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "experience_band IN ('0-1', '2-5', '6-10', '10+') OR experience_band IS NULL",
            name="check_teacher_experience_band",
        ),
        sa.CheckConstraint("address_form IN ('f', 'm')", name="check_teacher_address_form"),
        sa.CheckConstraint(
            "preferred_channel IN ('whatsapp', 'web')", name="check_teacher_preferred_channel"
        ),
    )

    op.create_table(
        "teacher_contact",
        sa.Column(
            "teacher_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("teacher.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("phone_enc", postgresql.BYTEA(), nullable=False),
    )

    op.create_table(
        "invite_code",
        sa.Column("code", sa.Text(), primary_key=True),
        sa.Column("cluster_id", sa.Text(), sa.ForeignKey("cluster.id"), nullable=True),
        sa.Column("batch_id", sa.Text(), sa.ForeignKey("batch.id"), nullable=True),
        sa.Column("district", sa.Text(), nullable=True),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
    )

    op.create_table(
        "arp_assignment",
        sa.Column(
            "arp_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app_user.id"),
            nullable=False,
        ),
        sa.Column("cluster_id", sa.Text(), sa.ForeignKey("cluster.id"), nullable=False),
        sa.PrimaryKeyConstraint("arp_user_id", "cluster_id"),
    )

    op.create_table(
        "consent_log",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "teacher_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("teacher.id"), nullable=True
        ),
        sa.Column("field", sa.Text(), nullable=False),
        sa.Column("value", sa.Boolean(), nullable=False),
        sa.Column("channel", sa.Text(), nullable=True),
        sa.Column("text_version", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    # ── Content ─────────────────────────────────────────────────────────────
    op.create_table(
        "content_release",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "published_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app_user.id"),
            nullable=True,
        ),
        sa.Column(
            "published_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )

    op.create_table(
        "move",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("release_id", sa.Text(), sa.ForeignKey("content_release.id"), nullable=False),
        sa.Column("domain", sa.Text(), nullable=False),
        sa.Column("title_hi", sa.Text(), nullable=False),
        sa.Column("sankul_month", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("approvals", postgresql.JSONB(), server_default=sa.text("'[]'"), nullable=False),
        sa.PrimaryKeyConstraint("id", "release_id"),
        sa.CheckConstraint(
            "status IN ('draft', 'in_review', 'approved')", name="check_move_status"
        ),
    )

    op.create_table(
        "persona",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("release_id", sa.Text(), sa.ForeignKey("content_release.id"), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.PrimaryKeyConstraint("id", "release_id"),
    )

    op.create_table(
        "bug_rule",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("kind", sa.Text(), nullable=True),
        sa.Column("code_ref", sa.Text(), nullable=False),
        sa.Column("description_hi", sa.Text(), nullable=True),
        sa.Column("research_ref", sa.Text(), nullable=True),
        sa.CheckConstraint("kind IN ('math', 'reading')", name="check_bug_rule_kind"),
    )

    # ── Sessions ─────────────────────────────────────────────────────────────
    op.create_table(
        "session_state",
        sa.Column(
            "teacher_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("teacher.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("week_start", sa.Date(), nullable=False),
        sa.Column("move_id", sa.Text(), nullable=False),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("prior_state", sa.Text(), nullable=True),
        sa.Column("rehearse_attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("context", postgresql.JSONB(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("teacher_id", "week_start"),
    )

    op.create_table(
        "move_path",
        sa.Column(
            "teacher_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("teacher.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("move_id", sa.Text(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("teacher_id", "position"),
    )

    op.create_table(
        "scene",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "teacher_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("teacher.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("move_id", sa.Text(), nullable=True),
        sa.Column("week_start", sa.Date(), nullable=True),
        sa.Column("attempt", sa.Integer(), nullable=True),
        sa.Column("mode", sa.Text(), server_default=sa.text("'normal'"), nullable=False),
        sa.Column("engine_state", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.Text(), server_default=sa.text("'active'"), nullable=False),
        sa.Column("end_reason", sa.Text(), nullable=True),
        sa.Column("teacher_turns", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("mode IN ('normal', 'placement', 'sankul')", name="check_scene_mode"),
        sa.CheckConstraint("status IN ('active', 'ended')", name="check_scene_status"),
    )

    op.create_table(
        "turn",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "teacher_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("teacher.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "scene_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("scene.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("idx", sa.Integer(), nullable=True),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("transcript", sa.Text(), nullable=True),
        sa.Column("stt_confidence", sa.Float(), nullable=True),
        sa.Column("acts", postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column("addressed_child", sa.Text(), nullable=True),
        sa.Column("problem", postgresql.JSONB(), nullable=True),
        sa.Column("rule_result", postgresql.JSONB(), nullable=True),
        sa.Column("line_hi", sa.Text(), nullable=True),
        sa.Column("guard_status", sa.Text(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("stage_ms", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    op.create_table(
        "message",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "teacher_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("teacher.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("direction", sa.Text(), nullable=False),
        sa.Column("channel", sa.Text(), nullable=False),
        sa.Column("channel_msg_id", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=True),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("audio_ref", sa.Text(), nullable=True),
        sa.Column("buttons", postgresql.JSONB(), nullable=True),
        sa.Column("speaker", sa.Text(), nullable=True),
        sa.Column("template_name", sa.Text(), nullable=True),
        sa.Column("state_at", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("direction IN ('in', 'out')", name="check_message_direction"),
        sa.UniqueConstraint("channel", "channel_msg_id", name="uq_channel_channel_msg_id"),
    )

    # ── Scores & Evidence ────────────────────────────────────────────────────
    op.create_table(
        "rehearsal_score",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "teacher_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("teacher.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "scene_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("scene.id"), nullable=True
        ),
        sa.Column("move_id", sa.Text(), nullable=True),
        sa.Column("attempt", sa.Integer(), nullable=True),
        sa.Column("scores", postgresql.JSONB(), nullable=False),
        sa.Column("evidence", postgresql.JSONB(), nullable=False),
        sa.Column("strength_hi", sa.Text(), nullable=True),
        sa.Column("change_hi", sa.Text(), nullable=True),
        sa.Column("exact_words_hi", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("needs_review", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("prompt_version", sa.Text(), nullable=True),
        sa.Column("model", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    op.create_table(
        "explain_score",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "teacher_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("teacher.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("move_id", sa.Text(), nullable=True),
        sa.Column("transcript", sa.Text(), nullable=True),
        sa.Column("points", postgresql.JSONB(), nullable=False),
        sa.Column("misconceptions", postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("needs_review", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("prompt_version", sa.Text(), nullable=True),
        sa.Column("model", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    op.create_table(
        "adoption_evidence",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "teacher_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("teacher.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("move_id", sa.Text(), nullable=False),
        sa.Column("level", sa.Integer(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("detail", postgresql.JSONB(), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("level BETWEEN 1 AND 5", name="check_adoption_evidence_level"),
        sa.CheckConstraint(
            "source IN ('rehearsal', 'reflection', 'peer_checklist', 'arp_observation', 'child_check')",
            name="check_adoption_evidence_source",
        ),
    )

    op.create_table(
        "realism_rating",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "teacher_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("teacher.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "scene_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("scene.id"), nullable=True
        ),
        sa.Column("rating", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("rating BETWEEN 1 AND 5", name="check_realism_rating_range"),
    )

    # ── Ask Any Time ─────────────────────────────────────────────────────────
    op.create_table(
        "question",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "teacher_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("teacher.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("category", sa.Text(), nullable=True),
        sa.Column(
            "clarifying_asked", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("answer_hi", sa.Text(), nullable=True),
        sa.Column("source_ids", postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("followup_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("followup_result", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('answered', 'escalated', 'arp_answered', 'closed')",
            name="check_question_status",
        ),
    )

    op.execute(
        """
        CREATE TABLE doc_chunk (
            id text PRIMARY KEY,
            source_id text NOT NULL,
            source_short_hi text,
            section text,
            page int,
            text text NOT NULL,
            tokens text[],
            embedding vector(1024),
            created_at timestamptz DEFAULT now()
        );
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_doc_chunk_embedding ON doc_chunk USING ivfflat (embedding vector_cosine_ops) WITH (lists = 50);"
    )

    # ── Review / Ops ─────────────────────────────────────────────────────────
    op.create_table(
        "review_item",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("kind", sa.Text(), nullable=True),
        sa.Column("ref_id", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), server_default=sa.text("'open'"), nullable=False),
        sa.Column("resolution", postgresql.JSONB(), nullable=True),
        sa.Column("resolved_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "kind IN ('rehearsal_score', 'explain_score', 'question', 'move', 'guard_failure')",
            name="check_review_item_kind",
        ),
        sa.CheckConstraint("status IN ('open', 'resolved')", name="check_review_item_status"),
    )

    op.create_table(
        "calibration_label",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "scene_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("scene.id"), nullable=True
        ),
        sa.Column(
            "explain_score_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("explain_score.id"),
            nullable=True,
        ),
        sa.Column(
            "coach_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app_user.id"),
            nullable=True,
        ),
        sa.Column("scores", postgresql.JSONB(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("blind", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    op.create_table(
        "arp_observation",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "arp_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app_user.id"),
            nullable=True,
        ),
        sa.Column(
            "teacher_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("teacher.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("move_id", sa.Text(), nullable=True),
        sa.Column("checklist", postgresql.JSONB(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("observed_on", sa.Date(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    op.create_table(
        "scheduled_job",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("run_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=True),
        sa.Column("status", sa.Text(), server_default=sa.text("'pending'"), nullable=False),
        sa.Column("attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'done', 'failed', 'cancelled')",
            name="check_scheduled_job_status",
        ),
    )
    op.create_index("ix_scheduled_job_status_run_at", "scheduled_job", ["status", "run_at"])

    op.create_table(
        "template_send",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("teacher_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("template_name", sa.Text(), nullable=True),
        sa.Column("category", sa.Text(), nullable=True),
        sa.Column("est_cost_inr", sa.Numeric(8, 3), nullable=True),
        sa.Column(
            "sent_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    op.create_table(
        "llm_call",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("role", sa.Text(), nullable=True),
        sa.Column("prompt_version", sa.Text(), nullable=True),
        sa.Column("model", sa.Text(), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("cache_read_tokens", sa.Integer(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("outcome", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    op.create_table(
        "tts_cache",
        sa.Column("key", sa.Text(), primary_key=True),
        sa.Column("voice", sa.Text(), nullable=True),
        sa.Column("text_hi", sa.Text(), nullable=True),
        sa.Column("mime", sa.Text(), nullable=True),
        sa.Column("bytes", postgresql.BYTEA(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    # ── Aggregates for Trainer View ──────────────────────────────────────────
    op.create_table(
        "agg_module_batch",
        sa.Column("batch_id", sa.Text(), nullable=False),
        sa.Column("move_id", sa.Text(), nullable=False),
        sa.Column("n_teachers", sa.Integer(), nullable=True),
        sa.Column("explain_missing", postgresql.JSONB(), nullable=True),
        sa.Column("rubric_dist", postgresql.JSONB(), nullable=True),
        sa.Column("ladder_dist", postgresql.JSONB(), nullable=True),
        sa.Column("active_rate", sa.Float(), nullable=True),
        sa.Column(
            "computed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("batch_id", "move_id"),
    )


def downgrade() -> None:
    op.drop_table("agg_module_batch")
    op.drop_table("tts_cache")
    op.drop_table("llm_call")
    op.drop_table("template_send")
    op.drop_index("ix_scheduled_job_status_run_at", table_name="scheduled_job")
    op.drop_table("scheduled_job")
    op.drop_table("arp_observation")
    op.drop_table("calibration_label")
    op.drop_table("review_item")
    op.execute("DROP INDEX IF EXISTS idx_doc_chunk_embedding;")
    op.drop_table("doc_chunk")
    op.drop_table("question")
    op.drop_table("realism_rating")
    op.drop_table("adoption_evidence")
    op.drop_table("explain_score")
    op.drop_table("rehearsal_score")
    op.drop_table("message")
    op.drop_table("turn")
    op.drop_table("scene")
    op.drop_table("move_path")
    op.drop_table("session_state")
    op.drop_table("bug_rule")
    op.drop_table("persona")
    op.drop_table("move")
    op.drop_table("content_release")
    op.drop_table("consent_log")
    op.drop_table("arp_assignment")
    op.drop_table("invite_code")
    op.drop_table("teacher_contact")
    op.drop_table("teacher")
    op.drop_table("app_user")
    op.drop_table("cluster")
    op.drop_table("batch")
