"""Add speech_spend and tts_audio tables.

Revision ID: b2d91f8c7e3a
Revises: 6a7a8609f2ce
Create Date: 2026-10-12 17:35:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b2d91f8c7e3a"
down_revision: str | None = "6a7a8609f2ce"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "speech_spend",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("units", sa.Integer(), nullable=False),
        sa.Column("cost_inr", sa.Float(), nullable=False),
        sa.CheckConstraint("kind IN ('stt', 'tts')", name="check_speech_spend_kind"),
    )

    op.create_table(
        "tts_audio",
        sa.Column("cache_key", sa.Text(), primary_key=True),
        sa.Column("ogg", postgresql.BYTEA(), nullable=True),
        sa.Column("mp3", postgresql.BYTEA(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("tts_audio")
    op.drop_table("speech_spend")
