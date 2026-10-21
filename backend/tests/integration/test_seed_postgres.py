"""Integration test: demo seed against real PostgreSQL (spec/03 §3.5).

Creates a throwaway database on the TEST_DATABASE_URL server, runs
`alembic upgrade head`, then `python -m backend.app.db.seed` twice (the same
commands scripts/start.sh runs on Render), and checks that the seed succeeds,
is idempotent and leaves no rows pointing at missing scenes.
Skipped locally if TEST_DATABASE_URL is not set.
"""

import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
REPO_ROOT = Path(__file__).resolve().parents[3]
SEED_TIMEOUT_S = 600

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL not set (runs in CI with real pgvector/pgvector:pg16)",
)

COUNTED_TABLES = (
    "cluster",
    "batch",
    "teacher",
    "app_user",
    "scene",
    "turn",
    "rehearsal_score",
    "explain_score",
    "adoption_evidence",
    "arp_observation",
    "move_path",
    "session_state",
    "doc_chunk",
)


def _sync_url(db_name: str | None = None) -> str:
    assert TEST_DATABASE_URL is not None
    url = make_url(TEST_DATABASE_URL).set(drivername="postgresql+psycopg2")
    if db_name is not None:
        url = url.set(database=db_name)
    return url.render_as_string(hide_password=False)


@pytest.fixture
def scratch_db() -> Iterator[str]:
    """Creates an empty database for this test and drops it afterwards."""
    db_name = f"abhyas_seed_{uuid4().hex[:10]}"
    admin = create_engine(_sync_url(), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{db_name}"'))
    try:
        yield db_name
    finally:
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{db_name}" WITH (FORCE)'))
        admin.dispose()


def _run(args: list[str], db_name: str) -> None:
    db_url = make_url(_sync_url(db_name))
    env = dict(os.environ)
    env.update(
        {
            "DATABASE_URL": db_url.set(drivername="postgresql+asyncpg").render_as_string(
                hide_password=False
            ),
            "ALEMBIC_DATABASE_URL": db_url.set(drivername="postgresql").render_as_string(
                hide_password=False
            ),
            "TEST_DATABASE_URL": db_url.set(drivername="postgresql").render_as_string(
                hide_password=False
            ),
            "PYTHONIOENCODING": "utf-8",
        }
    )
    proc = subprocess.run(
        [sys.executable, *args],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=SEED_TIMEOUT_S,
    )
    if proc.returncode != 0:
        # SQLAlchemy errors end with huge parameter dumps; surface the exception lines first
        error_lines = [
            line[:300]
            for line in proc.stderr.splitlines()
            if "Error:" in line or line.startswith("DETAIL:")
        ]
        pytest.fail(
            f"{' '.join(args)} exited {proc.returncode}\n"
            + "\n".join(error_lines[-6:])
            + f"\n--- stderr (tail) ---\n{proc.stderr[-1500:]}"
        )


def _counts(db_name: str) -> dict[str, int]:
    engine = create_engine(_sync_url(db_name))
    try:
        with engine.connect() as conn:
            return {
                table: int(conn.execute(text(f"SELECT count(*) FROM {table}")).scalar_one())
                for table in COUNTED_TABLES
            }
    finally:
        engine.dispose()


def _orphans(db_name: str) -> dict[str, int]:
    engine = create_engine(_sync_url(db_name))
    queries = {
        "rehearsal_score": (
            "SELECT count(*) FROM rehearsal_score r "
            "LEFT JOIN scene s ON s.id = r.scene_id "
            "WHERE r.scene_id IS NOT NULL AND s.id IS NULL"
        ),
        "turn": (
            "SELECT count(*) FROM turn t LEFT JOIN scene s ON s.id = t.scene_id WHERE s.id IS NULL"
        ),
    }
    try:
        with engine.connect() as conn:
            return {name: int(conn.execute(text(q)).scalar_one()) for name, q in queries.items()}
    finally:
        engine.dispose()


def test_seed_runs_on_fresh_postgres_and_is_idempotent(scratch_db: str) -> None:
    _run(["-m", "alembic", "upgrade", "head"], scratch_db)

    _run(["-m", "backend.app.db.seed"], scratch_db)
    first = _counts(scratch_db)
    assert first["scene"] > 0
    assert first["rehearsal_score"] == first["scene"]
    assert first["turn"] > 0
    assert first["app_user"] > 0
    assert _orphans(scratch_db) == {"rehearsal_score": 0, "turn": 0}

    _run(["-m", "backend.app.db.seed"], scratch_db)
    assert _counts(scratch_db) == first
