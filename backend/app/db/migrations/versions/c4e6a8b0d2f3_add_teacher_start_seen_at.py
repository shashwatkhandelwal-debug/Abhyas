"""Add teacher.start_seen_at: the one-time "Start here" screen was shown or skipped.

Revision ID: c4e6a8b0d2f3
Revises: b3d5f7a9c1e4
Create Date: 2026-10-23 19:30:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c4e6a8b0d2f3"
down_revision: str | None = "b3d5f7a9c1e4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("teacher", sa.Column("start_seen_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("teacher", "start_seen_at")
