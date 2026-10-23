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
    ClassOutcome,
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
            "class_struggles",
            "teaching_skills",
            "class_profile_prompted_at",
            "start_seen_at",
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
        "class_outcomes": await ids(ClassOutcome),
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
    teacher.class_struggles = ["NUM_COUNTING", "LIT_WRITING"]
    teacher.teaching_skills = ["probes_with_followup", "checks_on_new_problem"]
    teacher.class_profile_prompted_at = now
    teacher.start_seen_at = now
    session.add(
        ClassOutcome(
            teacher_id=teacher_id,
            move_id="NUM_ADD_CARRY_BUNDLES",
            answer="no",
            struggle_ids=["NUM_COUNTING"],
        )
    )
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
    # "My class": demo1 and demo2 start without a profile, demo3 has one seeded
    expected = {"teacher.demo3": ["LIT_MATRA_DROP", "NUM_ADD_CARRY"]}.get(login, [])
    assert after["profile"]["class_struggles"] == expected
    # "What do you want to get better at?": only demo3 starts with one
    assert after["profile"]["teaching_skills"] == (
        ["asks_to_explain"] if login == "teacher.demo3" else []
    )
    assert after["profile"]["class_profile_prompted_at"] is None
    assert after["profile"]["start_seen_at"] is None, "Start here shows again after a reset"
    assert after["class_outcomes"] == []
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
    # demo3 has a class choice, so its learn step says why this move was chosen
    from backend.app.class_profile.library import load_library
    from backend.app.db.seed import DEMO3_LEARN_MESSAGE_ID

    learn = await session.get(Message, DEMO3_LEARN_MESSAGE_ID)
    assert learn is not None
    reason = load_library().get("LIT_MATRA_DROP")
    assert reason is not None
    assert get_message("ui_class_chosen_because", lang="hi", label=reason.label_hi) in (
        learn.text or ""
    )

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


async def _class_struggles(session: AsyncSession, teacher_id: UUID) -> list[str]:
    teacher = await session.get(Teacher, teacher_id)
    assert teacher is not None
    await session.refresh(teacher)
    return list(teacher.class_struggles)


async def test_login_logout_cycle_keeps_demo3_class_profile_and_demo1_demo2_have_none(
    session: AsyncSession,
) -> None:
    from backend.app.db import seed

    ids = {name: DEMO_TEACHER_LOGINS[name][0] for name in sorted(DEMO_TEACHER_LOGINS)}
    for name in ids:
        await _dirty(session, ids[name])  # every demo teacher ends up with other struggles
    for name in ("teacher.demo1", "teacher.demo2", "teacher.demo3"):
        seed._LAST_DEMO_RESET.clear()
        await _login(session, name)
        await _logout(session, name)
    assert await _class_struggles(session, ids["teacher.demo3"]) == [
        "LIT_MATRA_DROP",
        "NUM_ADD_CARRY",
    ]
    assert await _class_struggles(session, ids["teacher.demo1"]) == []
    assert await _class_struggles(session, ids["teacher.demo2"]) == []
    for name, expected in (
        ("teacher.demo1", []),
        ("teacher.demo2", []),
        ("teacher.demo3", ["asks_to_explain"]),
    ):
        teacher = await session.get(Teacher, ids[name])
        assert teacher is not None
        await session.refresh(teacher)
        assert list(teacher.teaching_skills) == expected, name


async def test_too_short_scene_continue_and_skip_for_a_teacher_with_a_class_profile(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Real Postgres scene store + session state, demo3 (has a class profile)."""
    from backend.app.core.messages import get_message
    from backend.app.core.types import InboundMessage
    from backend.app.llm.schemas import ActTaggerOutput
    from backend.app.rehearsal import scene_store as ss
    from backend.app.rehearsal import stt_hints
    from backend.app.rehearsal.scene_runner import SceneRunner
    from backend.app.rule_engine.domain import TeachingAct
    from backend.app.sessions import service as service_module
    from backend.app.sessions.service import SessionService
    from backend.app.sessions.state_machine import OnboardingStateEnum, SessionStateEnum

    teacher_id = DEMO_TEACHER_LOGINS["teacher.demo3"][0]
    await _logout(session, "teacher.demo3")  # known start: the seeded state
    assert await _class_struggles(session, teacher_id)

    acts_by_prefix = {
        "तुमने कैसे": [TeachingAct.ASK_TO_EXPLAIN],
        "देखो, ये बंडल": [TeachingAct.CONCRETE_REPRESENTATION],
    }

    async def fake_tag_act(**_kwargs: Any) -> ActTaggerOutput:
        transcript = str(_kwargs.get("transcript", ""))
        acts = next((a for k, a in acts_by_prefix.items() if transcript.startswith(k)), [])
        return ActTaggerOutput(acts=acts, addressed_child=None, problem=None)

    store = ss.PostgresSceneStore()
    # DATABASE_URL set: the store reads and writes the scene and turn tables (no memory shortcut)
    monkeypatch.setattr(
        settings, "DATABASE_URL", session.bind.url.render_as_string(hide_password=False)
    )
    monkeypatch.setattr(
        ss, "async_session_factory", async_sessionmaker(session.bind, expire_on_commit=False)
    )  # type: ignore[arg-type]
    monkeypatch.setattr(service_module, "scene_store", store)
    monkeypatch.setattr(stt_hints, "scene_store", store)
    monkeypatch.setattr("backend.app.rehearsal.scene_runner.tag_act", fake_tag_act)

    service = SessionService(db_session=session, scene_runner=SceneRunner(store=store))

    async def say(text_: str | None = None, button: str | None = None) -> list[Any]:
        out = await service.handle_inbound(
            InboundMessage(
                channel="web",
                channel_msg_id=f"m-{uuid4().hex[:8]}",
                teacher_id=teacher_id,
                kind="button" if button else "text",
                text=text_,
                button_id=button,
                received_at=datetime.now(UTC),
            )
        )
        await session.commit()
        return out

    async def one_short_scene() -> list[Any]:
        ctx = await service.get_or_create_context(teacher_id)
        ctx.onboarding_state = OnboardingStateEnum.READY
        ctx.current_move_id = "NUM_SUB_REGROUP_BUNDLES"
        ctx.current_state = SessionStateEnum.MODEL
        await service._sync_context_to_db(ctx, teacher_id)
        await session.commit()
        await say(button="btn_listen")
        await say(button="btn_rehearse_one")
        await say(button="btn_child_ravi")
        await say("उल्टा घटा दिया, छोटी में से बड़ी")
        await say("तुमने कैसे किया? एक-एक कदम बताओ।")
        return await say("बस")

    out = await one_short_scene()
    assert out[-1].text_hi == get_message("scene_too_short", "f", done=1, needed=2, more=1)
    assert [b.id for b in out[-1].buttons or []] == ["btn_scene_continue", "btn_skip"]

    # continue: reopens the stored scene, the next reply counts, feedback follows
    out = await say(button="btn_scene_continue")
    assert out[0].text_hi == get_message("scene_resumed", "f")
    resumed = await store.get_active_for_teacher(teacher_id)
    assert resumed is not None
    # the stop marker is gone from the stored turns, so the next real turn can take its index
    assert [t.acts for t in resumed.turns] == [["ask_to_explain"]]
    await say("देखो, ये बंडल और तीलियाँ हैं। इन्हें गिनकर दिखाओ।")
    out = await say("बस")
    assert get_message("feedback_header", "f") in "\n".join(m.text_hi or "" for m in out)

    # skip: a fresh short scene, skipping moves on to try-in-class with no score
    await _logout(session, "teacher.demo3")
    out = await one_short_scene()
    assert [b.id for b in out[-1].buttons or []] == ["btn_scene_continue", "btn_skip"]
    await say(button="btn_skip")
    ctx = await service.get_or_create_context(teacher_id)
    assert ctx.current_state == SessionStateEnum.TRY_IN_CLASS
    assert await _class_struggles(session, teacher_id)  # profile untouched by the flow
