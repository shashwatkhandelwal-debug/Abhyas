"""Add class_visit_observation: an ARP's closed-list note after a class visit.

Additive only. Revision ID: b2d4f6a8c0e3, Revises: a1c3e5f7b9d2.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b2d4f6a8c0e3"
down_revision: str | None = "a1c3e5f7b9d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "class_visit_observation",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "teacher_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("teacher.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "arp_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app_user.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("talk_moves", postgresql.JSONB(), nullable=False),
        sa.Column("practice_seen", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("struggle_id", sa.Text(), nullable=True),
        sa.Column("next_step", sa.Text(), nullable=False),
        sa.Column("observed_on", sa.Date(), nullable=False),
        sa.Column("is_demo", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "next_step IN ('ask_named', 'ask_why', 'hold_answer', 'wait_time', 'repeat')",
            name="check_class_visit_next_step",
        ),
    )
    op.create_index(
        "idx_class_visit_observation_teacher",
        "class_visit_observation",
        ["teacher_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_class_visit_observation_teacher", table_name="class_visit_observation")
    op.drop_table("class_visit_observation")
