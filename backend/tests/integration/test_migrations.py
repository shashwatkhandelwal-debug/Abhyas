"""Integration tests for database migrations against real PostgreSQL (§14 T03).

Runs: alembic upgrade head -> alembic downgrade base -> alembic upgrade head.
Verifies all 31 tables, pgcrypto, and vector extensions are created.
Skipped locally if TEST_DATABASE_URL is not set.
"""

import os

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")


@pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL not set (runs in CI with real pgvector/pgvector:pg16)",
)
def test_alembic_migrations_round_trip() -> None:
    """Round-trip migration test: upgrade head -> downgrade base -> upgrade head."""
    assert TEST_DATABASE_URL is not None
    # Use sync psycopg2 driver for inspection
    if "postgresql+asyncpg://" in TEST_DATABASE_URL:
        sync_url = TEST_DATABASE_URL.replace("postgresql+asyncpg://", "postgresql+psycopg2://")
    elif TEST_DATABASE_URL.startswith("postgresql://"):
        sync_url = TEST_DATABASE_URL.replace("postgresql://", "postgresql+psycopg2://", 1)
    else:
        sync_url = TEST_DATABASE_URL
    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", sync_url)

    db_name = sync_url.rsplit("/", 1)[-1].split("?")[0].lower()
    is_ci = os.environ.get("CI") == "true" or os.environ.get("GITHUB_ACTIONS") == "true"
    if "test" not in db_name and not is_ci:
        pytest.skip(
            f"Refusing to run destructive migration test on database '{db_name}' "
            "(name must contain 'test' or CI must be set to prevent accidental drops)"
        )

    engine = create_engine(sync_url)
    try:
        with engine.connect() as conn:
            conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto;"))
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
            conn.commit()

        # 1. Upgrade to head
        command.upgrade(alembic_cfg, "head")

        inspector = inspect(engine)
        tables = set(inspector.get_table_names())
        expected_tables = {
            "batch",
            "cluster",
            "app_user",
            "teacher",
            "teacher_contact",
            "invite_code",
            "arp_assignment",
            "consent_log",
            "content_release",
            "move",
            "persona",
            "bug_rule",
            "session_state",
            "move_path",
            "scene",
            "turn",
            "message",
            "rehearsal_score",
            "explain_score",
            "adoption_evidence",
            "realism_rating",
            "question",
            "doc_chunk",
            "review_item",
            "calibration_label",
            "arp_observation",
            "scheduled_job",
            "template_send",
            "llm_call",
            "speech_spend",
            "tts_audio",
            "agg_module_batch",
        }
        for table in expected_tables:
            assert table in tables, f"Table {table} missing after upgrade"

        # Verify extensions
        with engine.connect() as conn:
            exts = {row[0] for row in conn.execute(text("SELECT extname FROM pg_extension"))}
            assert "vector" in exts
            assert "pgcrypto" in exts

        # 2. Downgrade to base
        command.downgrade(alembic_cfg, "base")
        inspector = inspect(engine)
        tables_after_downgrade = set(inspector.get_table_names())
        # All app tables should be dropped
        for table in expected_tables:
            assert table not in tables_after_downgrade, (
                f"Table {table} still exists after downgrade"
            )

        # 3. Upgrade to head again
        command.upgrade(alembic_cfg, "head")
        inspector = inspect(engine)
        tables_reupgrade = set(inspector.get_table_names())
        for table in expected_tables:
            assert table in tables_reupgrade, f"Table {table} missing after re-upgrade"
    finally:
        engine.dispose()
