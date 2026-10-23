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
from starlette.responses import Response

from backend.app.auth.router import logout
from backend.app.auth.session import create_session_token
from backend.app.config import settings
from backend.app.db.models import (
    AdoptionEvidence,
    AppUser,
    Message,
    ModuleProgress,
    MovePath,
    Question,
    RealismRating,
    RehearsalScore,
    Scene,
    SessionState,
    Teacher,
    TrainingRating,
    Turn,
)
from backend.app.db.seed import DEMO2_SCENE_ID, DEMO_TEACHER_LOGINS
from backend.app.web.admin import reset_demo_data

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
        "training_ratings": await ids(TrainingRating),
        "evidence": await ids(AdoptionEvidence),
        "module_progress": sorted(
            (m.module_id, m.check_passed, m.diagnose_verdict)
            for m in (
                await session.execute(
                    select(ModuleProgress).where(ModuleProgress.teacher_id == teacher_id)
                )
            )
            .scalars()
            .all()
        ),
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
    session.add(TrainingRating(teacher_id=teacher_id, rating=5, comment="बहुत अच्छा"))
    session.add(Question(teacher_id=teacher_id, text="नया सवाल", status="answered"))
    # module progress: demo3 already has the row (seeded complete), the others get a new one
    mp = await session.get(ModuleProgress, (teacher_id, "NUM_SUB_REGROUP_BUNDLES"))
    if mp is None:
        session.add(
            ModuleProgress(
                teacher_id=teacher_id,
                module_id="NUM_SUB_REGROUP_BUNDLES",
                learn_done_at=now,
                check_passed=True,
            )
        )
    else:
        mp.check_passed = False
        mp.diagnose_verdict = "wrong"
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
    # demo2 resumes inside a one-on-one scene with Ravi, so it starts with that chat history
    assert after["messages"] == (
        seeded["messages"] if login in ("teacher.demo2", "teacher.demo3") else []
    )
    assert after == seeded
    if login == "teacher.demo2":
        scene = await session.get(Scene, DEMO2_SCENE_ID)
        assert scene is not None and scene.status == "active"
        assert scene.engine_state["one_on_one"] is True
        assert scene.engine_state["teacher_turns"] == 1
        assert len(after["messages"]) == 5


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


async def _scene_one_on_one_state(session: AsyncSession, teacher_id: UUID) -> dict[str, Any]:
    state = (
        await session.execute(select(SessionState).where(SessionState.teacher_id == teacher_id))
    ).scalar_one()
    scene = await session.get(Scene, DEMO2_SCENE_ID)
    messages = (
        (await session.execute(select(Message).where(Message.teacher_id == teacher_id)))
        .scalars()
        .all()
    )
    return {
        "rehearse_mode": (state.context or {}).get("rehearse_mode"),
        "state": state.state,
        "scene_active": scene is not None and scene.status == "active",
        "messages": len(messages),
    }


async def test_admin_reset_restores_one_on_one_and_modules_like_logout(
    session: AsyncSession,
) -> None:
    demo2 = DEMO_TEACHER_LOGINS["teacher.demo2"][0]
    demo3 = DEMO_TEACHER_LOGINS["teacher.demo3"][0]
    await _dirty(session, demo2)
    await _dirty(session, demo3)
    await session.execute(text("DELETE FROM module_progress WHERE teacher_id = :t"), {"t": demo3})
    await session.commit()

    await reset_demo_data(session)
    admin_state = await _scene_one_on_one_state(session, demo2)
    assert admin_state["rehearse_mode"] == "one_on_one"
    assert admin_state["scene_active"] is True
    assert admin_state["messages"] == 5
    modules = (
        (await session.execute(select(ModuleProgress).where(ModuleProgress.teacher_id == demo3)))
        .scalars()
        .all()
    )
    assert len(modules) == 3

    await _dirty(session, demo2)
    await _logout(session, "teacher.demo2")
    assert await _scene_one_on_one_state(session, demo2) == admin_state


async def _demo3_learn_view(session: AsyncSession) -> dict[str, Any]:
    demo3 = DEMO_TEACHER_LOGINS["teacher.demo3"][0]
    state = (
        await session.execute(select(SessionState).where(SessionState.teacher_id == demo3))
    ).scalar_one()
    msgs = (
        (await session.execute(select(Message).where(Message.teacher_id == demo3))).scalars().all()
    )
    return {
        "state": state.state,
        "messages": len(msgs),
        "buttons": [[b["id"], b["title_hi"]] for b in (msgs[0].buttons or [])] if msgs else [],
        "text": msgs[0].text if msgs else None,
    }


async def test_demo3_starts_on_the_learning_step_with_two_buttons_and_logout_restores_it(
    session: AsyncSession,
) -> None:
    from backend.app.core.messages import get_message

    demo3 = DEMO_TEACHER_LOGINS["teacher.demo3"][0]
    seeded = await _demo3_learn_view(session)
    assert seeded["state"] == "LEARN"
    assert seeded["messages"] == 1
    assert seeded["buttons"] == [
        ["btn_understood", get_message("btn_understood", lang="hi")],
        ["btn_replay", get_message("btn_replay", lang="hi")],
    ]
    assert seeded["buttons"][0][1] == "समझ गई, आगे" and seeded["buttons"][1][1] == "फिर से सुनें"

    await _dirty(session, demo3)
    assert await _demo3_learn_view(session) != seeded
    await _logout(session, "teacher.demo3")
    assert await _demo3_learn_view(session) == seeded

    await _dirty(session, demo3)
    await reset_demo_data(session)
    assert await _demo3_learn_view(session) == seeded


async def _login(session: AsyncSession, username: str) -> None:
    from backend.app.auth.router import login

    request = Request(
        {
            "type": "http",
            "method": "POST",
            "headers": [(b"content-type", b"application/json")],
            "query_string": b"",
            "client": ("203.0.113.9", 1234),
        }
    )

    async def _json() -> dict[str, str]:
        return {"username": username, "password": settings.DEMO_PASSWORD}

    request.json = _json  # type: ignore[method-assign]
    resp = await login(request, Response(), session)
    assert resp.status_code == 200
    await session.commit()


@pytest.mark.parametrize("login_name", sorted(DEMO_TEACHER_LOGINS))
async def test_login_resets_dirty_demo_teacher_to_seed(
    session: AsyncSession, login_name: str
) -> None:
    from backend.app.db import seed

    teacher_id = DEMO_TEACHER_LOGINS[login_name][0]
    seeded = await _snapshot(session, teacher_id)
    await _dirty(session, teacher_id)
    assert await _snapshot(session, teacher_id) != seeded

    seed._LAST_DEMO_RESET.clear()  # earlier tests' resets must not trigger the debounce
    await _login(session, login_name)
    assert await _snapshot(session, teacher_id) == seeded


async def test_quick_second_login_does_not_wipe_again_but_new_messages_force_reset(
    session: AsyncSession,
) -> None:
    from backend.app.db import seed

    teacher_id = DEMO_TEACHER_LOGINS["teacher.demo1"][0]
    seed._LAST_DEMO_RESET.clear()
    await _login(session, "teacher.demo1")
    first = seed._LAST_DEMO_RESET[teacher_id]
    await _login(session, "teacher.demo1")
    assert seed._LAST_DEMO_RESET[teacher_id] == first  # skipped

    await _dirty(session, teacher_id)  # writes a message newer than the reset
    await _login(session, "teacher.demo1")
    assert seed._LAST_DEMO_RESET[teacher_id] > first


async def test_stale_scene_save_after_reset_is_silent(
    session: AsyncSession, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    import logging

    from backend.app.rehearsal.scene_store import PostgresSceneStore, SceneRecord
    from backend.app.rule_engine.domain import SceneState

    teacher_id = DEMO_TEACHER_LOGINS["teacher.demo1"][0]
    scene_id = uuid4()
    session.add(Scene(id=scene_id, teacher_id=teacher_id, move_id="NUM_SUB_REGROUP_BUNDLES",
                      engine_state={}))  # fmt: skip
    await session.commit()
    await _logout(session, "teacher.demo1")  # reset deletes the scene

    from backend.app.rehearsal import scene_store as ss

    monkeypatch.setattr(
        ss, "async_session_factory", async_sessionmaker(session.bind, expire_on_commit=False)
    )  # type: ignore[arg-type]
    store = PostgresSceneStore()
    record = SceneRecord.model_construct(  # type: ignore[call-arg]
        scene_id=scene_id, teacher_id=teacher_id, move_id="X", turns=[], active=True,
        scene_state=SceneState.model_construct(), created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )  # fmt: skip
    with caplog.at_level(logging.DEBUG, logger="abhyas.rehearsal.scene_store"):
        await store.save(record)
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]
