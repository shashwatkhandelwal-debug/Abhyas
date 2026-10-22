"""Add app_user.ui_lang and the message_translation cache table.

Revision ID: b4d6f8a0c2e5
Revises: a3c5e7f9b1d4
Create Date: 2026-10-22 12:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b4d6f8a0c2e5"
down_revision: str | None = "a3c5e7f9b1d4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "app_user",
        sa.Column("ui_lang", sa.Text(), nullable=True, server_default="hi"),
    )
    op.create_table(
        "message_translation",
        sa.Column(
            "message_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("message.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("lang", sa.Text(), primary_key=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("message_translation")
    op.drop_column("app_user", "ui_lang")
