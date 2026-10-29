"""Add the follow-up loop: class_followup, class_followup_outcome, teacher.tomorrow_focus_opt_in.

Additive only. Revision ID: a1c3e5f7b9d2, Revises: e9b1d3f5a7c2.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a1c3e5f7b9d2"
down_revision: str | None = "e9b1d3f5a7c2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "teacher",
        sa.Column(
            "tomorrow_focus_opt_in", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
    )
    op.create_table(
        "class_followup",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "teacher_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("teacher.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "checkin_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("class_checkin.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("struggle_id", sa.Text(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("offered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_demo", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("checkin_id", name="uq_class_followup_checkin"),
    )
    op.create_index("idx_class_followup_teacher", "class_followup", ["teacher_id", "due_date"])
    op.create_table(
        "class_followup_outcome",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "teacher_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("teacher.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "followup_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("class_followup.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("outcome", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("followup_id", name="uq_class_followup_outcome_followup"),
        sa.CheckConstraint(
            "outcome IN ('worked', 'stuck', 'cant')", name="check_class_followup_outcome"
        ),
        sa.CheckConstraint(
            "reason IS NULL OR reason IN ('time', 'multigrade', 'absent', 'other')",
            name="check_class_followup_reason",
        ),
    )
    op.create_index(
        "idx_class_followup_outcome_teacher",
        "class_followup_outcome",
        ["teacher_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_class_followup_outcome_teacher", table_name="class_followup_outcome")
    op.drop_table("class_followup_outcome")
    op.drop_index("idx_class_followup_teacher", table_name="class_followup")
    op.drop_table("class_followup")
    op.drop_column("teacher", "tomorrow_focus_opt_in")
