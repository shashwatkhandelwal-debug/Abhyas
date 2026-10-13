"""Drop unused tts_cache table.

Revision ID: c4e1f7a2b9d3
Revises: b2d91f8c7e3a
Create Date: 2026-10-13 11:55:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c4e1f7a2b9d3"
down_revision: str | None = "b2d91f8c7e3a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_table("tts_cache")


def downgrade() -> None:
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
