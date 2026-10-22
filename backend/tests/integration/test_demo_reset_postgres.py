"""Integration test: logging out of a shared demo teacher resets it to the seeded state.

Seeds a scratch Postgres (same commands as scripts/start.sh), dirties a demo teacher the way a
chat session would, calls the real /logout handler, and compares against a snapshot taken right
after seeding. Skipped locally if TEST_DATABASE_URL is not set.
"""

import os
import subprocess
import sys
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from starlette.requests import Request

from backend.app.auth.router import logout
from backend.app.auth.session import create_session_token
from backend.app.db.models import (
    AdoptionEvidence,
    AppUser,
    Message,
    MovePath,
    Question,
    RealismRating,
    RehearsalScore,
    Scene,
    SessionState,
    Teacher,
    Turn,
)
from backend.app.db.seed import DEMO_TEACHER_LOGINS

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
REPO_ROOT = Path(__file__).resolve().parents[3]
SEED_TIMEOUT_S = 600

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL not set (runs in CI with real pgvector/pgvector:pg16)",
)


def _url(db_name: str | None, driver: str) -> str:
    assert TEST_DATABASE_URL is not None
    url = make_url(TEST_DATABASE_URL).set(drivername=driver)
    if db_name is not None:
        url = url.set(database=db_name)
    return url.render_as_string(hide_password=False)


@pytest.fixture(scope="module")
def seeded_db() -> Iterator[str]:
    db_name = f"abhyas_reset_{uuid4().hex[:10]}"
    admin = create_engine(_url(None, "postgresql+psycopg2"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{db_name}"'))
    try:
        env = dict(os.environ)
        env.update(
            {
                "DATABASE_URL": _url(db_name, "postgresql+asyncpg"),
                "ALEMBIC_DATABASE_URL": _url(db_name, "postgresql"),
                "TEST_DATABASE_URL": _url(db_name, "postgresql"),
                "PYTHONIOENCODING": "utf-8",
            }
        )
        for args in (["-m", "alembic", "upgrade", "head"], ["-m", "backend.app.db.seed"]):
            proc = subprocess.run(
                [sys.executable, *args],
                cwd=REPO_ROOT,
                env=env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=SEED_TIMEOUT_S,
            )
            assert proc.returncode == 0, proc.stderr[-1500:]
        yield db_name
    finally:
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{db_name}" WITH (FORCE)'))
        admin.dispose()


@pytest.fixture
async def session(seeded_db: str) -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(_url(seeded_db, "postgresql+asyncpg"), poolclass=NullPool)
    async with async_sessionmaker(engine, expire_on_commit=False)() as s:
        yield s
    await engine.dispose()


async def _snapshot(session: AsyncSession, teacher_id: UUID) -> dict[str, Any]:
    """Everything the reset promises to restore, as comparable plain data."""
    teacher = await session.get(Teacher, teacher_id)
    assert teacher is not None
    await session.refresh(teacher)
    profile = {
        c: getattr(teacher, c)
        for c in (
            "name",
            "onboarding_state",
            "classes",
            "consent_service",
            "consent_share_scores",
            "consent_class_audio",
            "consent_research",
            "address_form",
            "lite_mode",
            "phone_hash",
            "preferred_channel",
            "cluster_id",
            "batch_id",
        )
    }

    async def ids(model: Any) -> list[str]:
        rows = (await session.execute(select(model.id).where(model.teacher_id == teacher_id))).all()
        return sorted(str(r[0]) for r in rows)

    states = (
        (await session.execute(select(SessionState).where(SessionState.teacher_id == teacher_id)))
        .scalars()
        .all()
    )
    path = (
        (await session.execute(select(MovePath).where(MovePath.teacher_id == teacher_id)))
        .scalars()
        .all()
    )
    return {
        "profile": profile,
        "messages": await ids(Message),
        "session_state": sorted(
            (str(s.week_start), s.move_id, s.state, s.prior_state, s.rehearse_attempts)
            for s in states
        ),
        "move_path": sorted((p.position, p.move_id) for p in path),
        "scenes": await ids(Scene),
        "turns": await ids(Turn),
        "rehearsal_scores": await ids(RehearsalScore),
        "questions": await ids(Question),
        "ratings": await ids(RealismRating),
        "evidence": await ids(AdoptionEvidence),
    }


async def _dirty(session: AsyncSession, teacher_id: UUID) -> None:
    """Mimics what a judge's chat session writes."""
    now = datetime.now(UTC)
    teacher = await session.get(Teacher, teacher_id)
    assert teacher is not None
    teacher.onboarding_state = "PROFILE_NAME"
    teacher.name = "बदला हुआ नाम"
    teacher.classes = [1]
    teacher.consent_share_scores = not teacher.consent_share_scores
    teacher.consent_research = True
    teacher.lite_mode = True
    session.add(
        Message(
            teacher_id=teacher_id,
            direction="in",
            channel="web",
            channel_msg_id=f"c-{uuid4()}",
            kind="text",
            text="पुराना संदेश",
            created_at=now,
            updated_at=now,
        )  # fmt: skip
    )
    await session.execute(
        text("DELETE FROM session_state WHERE teacher_id = :t"), {"t": teacher_id}
    )
    today = date.today()
    session.add(
        SessionState(
            teacher_id=teacher_id,
            week_start=today - timedelta(days=today.weekday()),
            move_id="NUM_PLACE_VALUE_BUNDLES",
            state="DONE",
            rehearse_attempts=3,
            context={},
        )
    )
    session.add(MovePath(teacher_id=teacher_id, position=99, move_id="X", reason="chat"))
    scene = Scene(
        id=uuid4(), teacher_id=teacher_id, move_id="NUM_SUB_REGROUP_BUNDLES", engine_state={}
    )
    session.add(scene)
    await session.flush()
    session.add(
        Turn(teacher_id=teacher_id, scene_id=scene.id, idx=1, role="teacher", transcript="x")
    )
    session.add(RealismRating(teacher_id=teacher_id, scene_id=scene.id, rating=4))
    session.add(Question(teacher_id=teacher_id, text="नया सवाल", status="answered"))
    session.add(
        AdoptionEvidence(teacher_id=teacher_id, move_id="NUM_SUB_REGROUP_BUNDLES", level=1,
                         source="rehearsal", detail={}, created_at=now)
    )  # fmt: skip
    await session.commit()


async def _logout(session: AsyncSession, username: str) -> None:
    user = (await session.execute(select(AppUser).where(AppUser.username == username))).scalar_one()
    token = create_session_token(
        {"user_id": str(user.id), "username": user.username, "role": user.role}
    )
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "headers": [(b"authorization", f"Bearer {token}".encode()), (b"accept", b"*/*")],
            "query_string": b"",
        }
    )
    resp = await logout(request, session)
    assert resp.status_code == 303
    await session.commit()


@pytest.mark.parametrize("login", sorted(DEMO_TEACHER_LOGINS))
async def test_logout_resets_demo_teacher_to_seed(session: AsyncSession, login: str) -> None:
    teacher_id = DEMO_TEACHER_LOGINS[login][0]
    seeded = await _snapshot(session, teacher_id)

    await _dirty(session, teacher_id)
    assert await _snapshot(session, teacher_id) != seeded

    await _logout(session, login)
    after = await _snapshot(session, teacher_id)
    assert after["messages"] == []
    assert after == seeded


async def test_logout_does_not_reset_a_non_demo_teacher(session: AsyncSession) -> None:
    teacher = Teacher(id=uuid4(), name="असली शिक्षिका", preferred_channel="web", is_demo=False)
    user = AppUser(
        id=uuid4(), username="real.teacher", role="teacher", teacher_id=teacher.id,
        password_hash="x", is_demo=False,
    )  # fmt: skip
    session.add_all([teacher, user])
    await session.flush()
    now = datetime.now(UTC)
    session.add(
        Message(
            teacher_id=teacher.id,
            direction="in",
            channel="web",
            channel_msg_id=f"r-{uuid4()}",
            kind="text",
            text="रखना है",
            created_at=now,
            updated_at=now,
        )  # fmt: skip
    )
    await session.commit()

    await _logout(session, "real.teacher")
    count = (
        (await session.execute(select(Message).where(Message.teacher_id == teacher.id)))
        .scalars()
        .all()
    )
    assert len(count) == 1
    assert (await session.get(Teacher, teacher.id)).name == "असली शिक्षिका"  # type: ignore[union-attr]


async def test_reset_failure_does_not_block_logout(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def boom(*_a: Any, **_k: Any) -> bool:
        raise RuntimeError("reset exploded")

    monkeypatch.setattr("backend.app.db.seed.reset_demo_teacher", boom)
    await _logout(session, "teacher.demo2")  # asserts the 303 inside
