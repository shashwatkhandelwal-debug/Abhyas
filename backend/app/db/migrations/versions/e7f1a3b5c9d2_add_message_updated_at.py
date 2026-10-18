"""Add updated_at column to message table for text-first audio polling.

Revision ID: e7f1a3b5c9d2
Revises: c4e1f7a2b9d3
Create Date: 2026-10-18 07:55:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e7f1a3b5c9d2"
down_revision: str | None = "c4e1f7a2b9d3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "message",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("message", "updated_at")
