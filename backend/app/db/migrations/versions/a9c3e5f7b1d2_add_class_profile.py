"""Add the class profile: teacher.class_struggles, class_profile_prompted_at and class_outcome.

Revision ID: a9c3e5f7b1d2
Revises: f8a2b4c6d1e7
Create Date: 2026-10-23 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a9c3e5f7b1d2"
down_revision: str | None = "f8a2b4c6d1e7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "teacher",
        sa.Column(
            "class_struggles",
            postgresql.JSONB(),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "teacher", sa.Column("class_profile_prompted_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_table(
        "class_outcome",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "teacher_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("teacher.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("move_id", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("struggle_ids", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("answer IN ('yes', 'some', 'no')", name="check_class_outcome_answer"),
    )
    op.create_index("idx_class_outcome_teacher", "class_outcome", ["teacher_id", "move_id"])


def downgrade() -> None:
    op.drop_index("idx_class_outcome_teacher", table_name="class_outcome")
    op.drop_table("class_outcome")
    op.drop_column("teacher", "class_profile_prompted_at")
    op.drop_column("teacher", "class_struggles")
