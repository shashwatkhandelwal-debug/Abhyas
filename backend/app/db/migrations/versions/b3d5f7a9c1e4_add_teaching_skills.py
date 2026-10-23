"""Add teacher.teaching_skills: what the teacher wants to get better at (closed list, at most 2).

Revision ID: b3d5f7a9c1e4
Revises: a9c3e5f7b1d2
Create Date: 2026-10-23 16:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b3d5f7a9c1e4"
down_revision: str | None = "a9c3e5f7b1d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "teacher",
        sa.Column(
            "teaching_skills",
            postgresql.JSONB(),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("teacher", "teaching_skills")
