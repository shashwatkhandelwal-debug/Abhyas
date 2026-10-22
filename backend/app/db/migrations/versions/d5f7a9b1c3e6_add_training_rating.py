"""Add training_rating table ("rate the training" after REFLECT).

Revision ID: d5f7a9b1c3e6
Revises: b4d6f8a0c2e5
Create Date: 2026-10-22 16:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d5f7a9b1c3e6"
down_revision: str | None = "b4d6f8a0c2e5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "training_rating",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "teacher_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("teacher.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("move_id", sa.Text(), nullable=True),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("rating BETWEEN 1 AND 5", name="check_training_rating_range"),
    )
    op.create_index("ix_training_rating_teacher_id", "training_rating", ["teacher_id"])


def downgrade() -> None:
    op.drop_index("ix_training_rating_teacher_id", table_name="training_rating")
    op.drop_table("training_rating")
