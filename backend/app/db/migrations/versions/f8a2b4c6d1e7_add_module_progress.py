"""Add module_progress table (modules: learn, diagnose a child, practise, check).

Revision ID: f8a2b4c6d1e7
Revises: d5f7a9b1c3e6
Create Date: 2026-10-22 19:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f8a2b4c6d1e7"
down_revision: str | None = "d5f7a9b1c3e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "module_progress",
        sa.Column(
            "teacher_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("teacher.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("module_id", sa.Text(), primary_key=True),
        sa.Column("learn_done_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("diagnose_done_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("diagnose_verdict", sa.Text(), nullable=True),
        sa.Column("practise_done_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("check_done_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("check_passed", sa.Boolean(), nullable=True),
        sa.Column("check_covered", postgresql.JSONB(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "diagnose_verdict IS NULL OR diagnose_verdict IN "
            "('correct', 'partly', 'wrong', 'skipped')",
            name="check_module_progress_verdict",
        ),
    )


def downgrade() -> None:
    op.drop_table("module_progress")
