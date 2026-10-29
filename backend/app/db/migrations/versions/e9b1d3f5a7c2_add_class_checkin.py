"""Add class_checkin table ("After class: how did it go?").

Revision ID: e9b1d3f5a7c2
Revises: c4e6a8b0d2f3
Create Date: 2026-10-29 14:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e9b1d3f5a7c2"
down_revision: str | None = "c4e6a8b0d2f3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "class_checkin",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "teacher_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("teacher.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("module_id", sa.Text(), nullable=False),
        sa.Column("outcome", sa.Text(), nullable=False),
        sa.Column("struggle_ids", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "outcome IN ('well', 'some', 'most')", name="check_class_checkin_outcome"
        ),
    )
    op.create_index("idx_class_checkin_teacher", "class_checkin", ["teacher_id", "created_at"])


def downgrade() -> None:
    op.drop_index("idx_class_checkin_teacher", table_name="class_checkin")
    op.drop_table("class_checkin")
