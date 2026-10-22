"""Add citations JSONB column to message for tappable guide-answer sources.

Revision ID: a3c5e7f9b1d4
Revises: e7f1a3b5c9d2
Create Date: 2026-10-22 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a3c5e7f9b1d4"
down_revision: str | None = "e7f1a3b5c9d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "message", sa.Column("citations", postgresql.JSONB(astext_type=sa.Text()), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("message", "citations")
