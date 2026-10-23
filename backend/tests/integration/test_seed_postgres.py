"""Integration test: demo seed against real PostgreSQL (spec/03 §3.5).

Creates a throwaway database on the TEST_DATABASE_URL server, runs
`alembic upgrade head`, then `python -m backend.app.db.seed` twice (the same
commands scripts/start.sh runs on Render), and checks that the seed succeeds,
is idempotent, leaves no rows pointing at missing scenes, repairs legacy
onboarding states, and that every seeded teacher's SessionContext loads.
Skipped locally if TEST_DATABASE_URL is not set.
"""

import asyncio
import os
import re
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from backend.app.sessions.service import SessionService
from backend.app.sessions.state_machine import OnboardingStateEnum

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
REPO_ROOT = Path(__file__).resolve().parents[3]
SEED_TIMEOUT_S = 600
# "pkg.ExcName: message" and "DETAIL:  ..." lines (not "INFO:logger:..." log lines)
EXCEPTION_LINE = re.compile(r"^[A-Za-z_][\w.]*: ")

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
    "review_item",
    "question",
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
            line[:300] for line in proc.stderr.splitlines() if EXCEPTION_LINE.match(line)
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


def _review_queue(db_name: str) -> list[tuple[str, str, str, bool]]:
    """(kind, ref_id, status, the referenced row exists) for every review item."""
    engine = create_engine(_sync_url(db_name))
    query = (
        "SELECT r.kind, r.ref_id, r.status, "
        "CASE r.kind "
        " WHEN 'rehearsal_score' THEN EXISTS (SELECT 1 FROM rehearsal_score x WHERE x.id::text = r.ref_id) "
        " WHEN 'explain_score' THEN EXISTS (SELECT 1 FROM explain_score x WHERE x.id::text = r.ref_id) "
        " WHEN 'question' THEN EXISTS (SELECT 1 FROM question x WHERE x.id::text = r.ref_id) "
        " ELSE false END "
        "FROM review_item r ORDER BY r.created_at"
    )
    try:
        with engine.connect() as conn:
            return [
                (str(k), str(ref), str(st), bool(found))
                for k, ref, st, found in conn.execute(text(query))
            ]
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
    # every finished scene is scored; demo2's live one-on-one scene has no score yet
    assert first["rehearsal_score"] == first["scene"] - 1
    assert first["turn"] > 0
    assert first["app_user"] > 0
    assert _orphans(scratch_db) == {"rehearsal_score": 0, "turn": 0}
    # the coach queue starts with a small, believable set of real rows, not one item per teacher
    queue = _review_queue(scratch_db)
    assert 3 <= len(queue) <= 8, queue
    assert {kind for kind, _ref, status, _found in queue} <= {
        "rehearsal_score",
        "explain_score",
        "question",
    }
    assert {status for _kind, _ref, status, _found in queue} == {"open"}
    assert all(found for _kind, _ref, _status, found in queue), "every item points at a real row"
    assert first["review_item"] == len(queue) and first["question"] == 1

    _run(["-m", "backend.app.db.seed"], scratch_db)
    assert _counts(scratch_db) == first

    # Live DBs seeded by the old code hold onboarding_state='COMPLETE' and move ids with no
    # move card (m_sub_regroup_intro, ...); one re-run must repair both
    _execute(
        scratch_db,
        "UPDATE teacher SET onboarding_state = 'COMPLETE' WHERE onboarding_state = 'READY'",
    )
    for new_id, legacy_id in LEGACY_MOVE_IDS.items():
        for table in ("session_state", "move_path", "adoption_evidence"):
            _execute(
                scratch_db,
                f"UPDATE {table} SET move_id = '{legacy_id}' "
                f"WHERE move_id = '{new_id}' AND teacher_id IN ({DEMO_TEACHER_IDS_SQL})",
            )
    assert _invalid_onboarding_count(scratch_db) > 0
    assert _move_ids_without_card(scratch_db)
    _run(["-m", "backend.app.db.seed"], scratch_db)
    assert _invalid_onboarding_count(scratch_db) == 0
    assert _move_ids_without_card(scratch_db) == []
    assert _counts(scratch_db) == first

    # The first chat message calls get_or_create_context; it must load for every seeded teacher
    failures = asyncio.run(_context_failures(scratch_db))
    assert failures == {}, (
        f"get_or_create_context raised for {len(failures)} teacher(s): {failures}"
    )


MOVES_DIR = REPO_ROOT / "content" / "moves"
LEGACY_MOVE_IDS = {  # real card id -> id written by older seeds
    "NUM_SUB_REGROUP_BUNDLES": "m_sub_regroup_intro",
    "NUM_ADD_CARRY_BUNDLES": "m_count_forward_10",
    "NUM_PLACE_VALUE_BUNDLES": "m_place_value_bundling",
}
DEMO_TEACHER_IDS_SQL = ", ".join(f"'00000000-0000-0000-0000-00000000000{n}'" for n in (1, 2, 3))


def _move_ids_without_card(db_name: str) -> list[str]:
    engine = create_engine(_sync_url(db_name))
    query = (
        "SELECT move_id FROM session_state UNION SELECT move_id FROM move_path "
        "UNION SELECT move_id FROM adoption_evidence UNION SELECT move_id FROM scene "
        "UNION SELECT context->>'current_move_id' FROM session_state"
    )
    try:
        with engine.connect() as conn:
            move_ids = {row[0] for row in conn.execute(text(query)) if row[0]}
    finally:
        engine.dispose()
    return sorted(m for m in move_ids if not (MOVES_DIR / f"{m}.yaml").is_file())


def _execute(db_name: str, sql: str) -> None:
    engine = create_engine(_sync_url(db_name))
    try:
        with engine.begin() as conn:
            conn.execute(text(sql))
    finally:
        engine.dispose()


def _invalid_onboarding_count(db_name: str) -> int:
    valid = [state.value for state in OnboardingStateEnum]
    engine = create_engine(_sync_url(db_name))
    try:
        with engine.connect() as conn:
            return int(
                conn.execute(
                    text("SELECT count(*) FROM teacher WHERE NOT (onboarding_state = ANY(:valid))"),
                    {"valid": valid},
                ).scalar_one()
            )
    finally:
        engine.dispose()


async def _context_failures(db_name: str) -> dict[str, str]:
    async_url = make_url(_sync_url(db_name)).set(drivername="postgresql+asyncpg")
    engine = create_async_engine(async_url, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    failures: dict[str, str] = {}
    try:
        async with factory() as session:
            rows = await session.execute(text("SELECT id FROM teacher ORDER BY id"))
            teacher_ids: list[UUID] = [row[0] for row in rows]
        assert len(teacher_ids) == 51
        for teacher_id in teacher_ids:
            async with factory() as session:
                try:
                    await SessionService(db_session=session).get_or_create_context(teacher_id)
                except Exception as exc:  # collect all failures for one readable assertion
                    failures[str(teacher_id)] = f"{type(exc).__name__}: {exc}"
    finally:
        await engine.dispose()
    return failures


def test_reseed_tolerates_duplicate_adoption_evidence(scratch_db: str) -> None:
    """Live use writes several evidence rows per (teacher, move, level); the seed must not crash."""
    _run(["-m", "alembic", "upgrade", "head"], scratch_db)
    _run(["-m", "backend.app.db.seed"], scratch_db)
    engine = create_engine(_sync_url(scratch_db))
    try:
        with engine.begin() as conn:
            row = conn.execute(
                text(
                    "SELECT teacher_id, move_id, level FROM adoption_evidence ae "
                    "WHERE EXISTS (SELECT 1 FROM module_progress mp WHERE mp.teacher_id = ae.teacher_id) "
                    "AND teacher_id > '00000000-0000-0000-0000-000000000010' LIMIT 1"
                )
            ).one()
            conn.execute(
                text(
                    "INSERT INTO adoption_evidence (id, teacher_id, move_id, level, source, detail, created_at) "
                    "VALUES (:i, :t, :m, :l, 'rehearsal', '{}', now())"
                ),
                {"i": uuid4(), "t": row[0], "m": row[1], "l": row[2]},
            )
            dup = conn.execute(
                text(
                    "SELECT count(*) FROM adoption_evidence "
                    "WHERE teacher_id = :t AND move_id = :m AND level = :l"
                ),
                {"t": row[0], "m": row[1], "l": row[2]},
            ).scalar_one()
            assert dup == 2
    finally:
        engine.dispose()

    _run(["-m", "backend.app.db.seed"], scratch_db)  # must not raise MultipleResultsFound

    engine = create_engine(_sync_url(scratch_db))
    try:
        with engine.connect() as conn:
            cohort_modules = conn.execute(
                text(
                    "SELECT count(*) FROM module_progress "
                    "WHERE teacher_id > '00000000-0000-0000-0000-000000000010'"
                )
            ).scalar_one()
            remaining = conn.execute(
                text(
                    "SELECT count(*) FROM adoption_evidence "
                    "WHERE teacher_id = :t AND move_id = :m AND level = :l"
                ),
                {"t": row[0], "m": row[1], "l": row[2]},
            ).scalar_one()
        assert cohort_modules >= 40
        assert remaining == 1
    finally:
        engine.dispose()
