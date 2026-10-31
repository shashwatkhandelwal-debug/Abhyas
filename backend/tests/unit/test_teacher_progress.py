"""Unit tests for Teacher Progress Page, Consent Controls, and Account Deletion (spec/09 §9.2, T29).

Tests:
1. GET /teacher/progress requires teacher authentication (401 without auth, 403 for non-teacher).
2. Renders evidence ladder, scores, and covered key points correctly.
3. POST /teacher/consent toggles consent and creates ConsentLog.
4. GET /teacher/delete renders confirmation dialog with [हाँ, मिटाएँ] and [नहीं, वापस जाएँ].
5. POST /teacher/delete purges data (rehearsals, turns, scores, explain scores, evidence, sessions, consent logs) and logs out.
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, date, datetime
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from httpx import ASGITransport, AsyncClient

from backend.app.auth.guards import get_current_user
from backend.app.auth.session import SESSION_COOKIE_NAME, create_session_token
from backend.app.db.models import (
    AdoptionEvidence,
    AppUser,
    ConsentLog,
    ExplainScore,
    Message,
    MovePath,
    Question,
    RehearsalScore,
    ReviewItem,
    Scene,
    ScheduledJob,
    SessionState,
    Teacher,
    Turn,
)
from backend.app.db.session import get_db_session
from backend.app.web.teacher import STATIC_DIR
from backend.app.web.teacher import router as teacher_router

# ── Mock Result Helper ───────────────────────────────────────────────────────


class MockScalars:
    def __init__(self, items: list[Any]) -> None:
        self._items = items

    def all(self) -> list[Any]:
        return list(self._items)

    def first(self) -> Any:
        return self._items[0] if self._items else None


class MockResult:
    def __init__(self, value: Any = None, items: list[Any] | None = None) -> None:
        self._value = value
        self._items = items if items is not None else ([value] if value is not None else [])

    def scalar_one_or_none(self) -> Any:
        return self._value

    def scalar(self) -> Any:
        return self._value

    def scalars(self) -> MockScalars:
        return MockScalars(self._items)


# ── In-Memory Database Session ───────────────────────────────────────────────


class InMemoryProgressSession:
    """In-memory mock session supporting CRUD and purge queries for teacher progress tests."""

    def __init__(self, entities: list[Any] | None = None) -> None:
        self.entities: list[Any] = list(entities or [])
        self.added: list[Any] = []
        self.deleted: list[Any] = []

    def add(self, obj: Any) -> None:
        self.entities.append(obj)
        self.added.append(obj)

    async def get(self, model: type, ident: Any) -> Any:
        for obj in self.entities:
            if isinstance(obj, model) and getattr(obj, "id", None) == ident:
                return obj
        return None

    async def flush(self) -> None:
        pass

    async def commit(self) -> None:
        pass

    async def execute(self, stmt: Any) -> MockResult:
        sql = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        sql_lower = sql.lower()

        # DELETE statements
        if "delete from" in sql_lower:
            target_table = re.search(r"delete from (\w+)", sql, re.IGNORECASE)
            if target_table:
                tbl = target_table.group(1).lower()
                to_remove: list[Any] = []
                for obj in self.entities:
                    cls_name = obj.__class__.__name__.lower()
                    tbl_name = getattr(obj, "__tablename__", "").lower()
                    if tbl in (cls_name, tbl_name):
                        if isinstance(obj, ScheduledJob):
                            p = obj.payload or {}
                            t_str = str(p.get("teacher_id", ""))
                            q_str = str(p.get("question_id", ""))
                            if (t_str and t_str in sql) or (q_str and q_str in sql):
                                to_remove.append(obj)
                            elif not ("payload" in sql_lower or "json" in sql_lower):
                                to_remove.append(obj)
                        elif isinstance(obj, ReviewItem):
                            if obj.ref_id in sql or "ref_id" not in sql_lower:
                                to_remove.append(obj)
                        elif hasattr(obj, "teacher_id"):
                            tid_str = str(obj.teacher_id).lower().replace("-", "")
                            if (
                                str(obj.teacher_id) in sql
                                or tid_str in sql.lower().replace("-", "")
                                or "teacher_id" not in sql_lower
                            ):
                                to_remove.append(obj)
                        else:
                            to_remove.append(obj)
                for obj in to_remove:
                    self.entities.remove(obj)
                    self.deleted.append(obj)
            return MockResult(None)

        # SELECT queries
        if "from teacher" in sql_lower:
            match_id = re.search(r"id = '([^']+)'", sql, re.IGNORECASE)
            if match_id:
                tid = match_id.group(1).replace("-", "").lower()
                matches = [
                    t
                    for t in self.entities
                    if isinstance(t, Teacher) and str(t.id).replace("-", "").lower() == tid
                ]
                val = matches[0] if matches else None
                return MockResult(value=val, items=matches)
            all_teachers = [t for t in self.entities if isinstance(t, Teacher)]
            return MockResult(value=all_teachers[0] if all_teachers else None, items=all_teachers)

        if "max(adoption_evidence.level)" in sql_lower or "max(" in sql_lower:
            evs = [obj for obj in self.entities if isinstance(obj, AdoptionEvidence)]
            max_lvl = max([e.level for e in evs], default=0) if evs else 0
            return MockResult(value=max_lvl, items=[max_lvl])

        if "distinct" in sql_lower and "adoption_evidence.move_id" in sql_lower:
            ev_mids = list(
                {obj.move_id for obj in self.entities if isinstance(obj, AdoptionEvidence)}
            )
            return MockResult(items=ev_mids)

        if "distinct" in sql_lower and "rehearsal_score.move_id" in sql_lower:
            rs_mids = list(
                {obj.move_id for obj in self.entities if isinstance(obj, RehearsalScore)}
            )
            return MockResult(items=rs_mids)

        if "from move_path" in sql_lower:
            mps = [obj for obj in self.entities if isinstance(obj, MovePath)]
            return MockResult(items=mps)

        if "from session_state" in sql_lower:
            sss = [obj for obj in self.entities if isinstance(obj, SessionState)]
            return MockResult(items=sss)

        if "from rehearsal_score" in sql_lower:
            rscores = [obj for obj in self.entities if isinstance(obj, RehearsalScore)]
            return MockResult(items=rscores)

        if re.search(r"select\s+explain_score\.id\s+from", sql_lower):
            escores = [obj for obj in self.entities if isinstance(obj, ExplainScore)]
            return MockResult(items=[e.id for e in escores])

        if re.search(r"select\s+question\.id\s+from", sql_lower):
            questions = [obj for obj in self.entities if isinstance(obj, Question)]
            return MockResult(items=[q.id for q in questions])

        if "from explain_score" in sql_lower:
            escores = [obj for obj in self.entities if isinstance(obj, ExplainScore)]
            val = escores[-1] if escores else None
            return MockResult(value=val, items=escores)

        if "from scene" in sql_lower:
            scenes = [obj for obj in self.entities if isinstance(obj, Scene)]
            scene_ids = [s.id for s in scenes]
            return MockResult(items=scene_ids)

        return MockResult(None)


# ── App & Client Fixture Helper ──────────────────────────────────────────────


def create_test_progress_app(session: InMemoryProgressSession, user: AppUser | None) -> FastAPI:
    app = FastAPI()
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    app.include_router(teacher_router)

    if user is not None:
        app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db_session] = lambda: session

    return app


# ── Tests ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_progress_unauthenticated() -> None:
    """GET /teacher/progress requires teacher authentication (401 without auth)."""
    session = InMemoryProgressSession()
    app = create_test_progress_app(session, user=None)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/teacher/progress")
        assert res.status_code == 401


@pytest.mark.asyncio
async def test_get_progress_forbidden_for_other_roles() -> None:
    """GET /teacher/progress returns 403 Forbidden for non-teacher users."""
    session = InMemoryProgressSession()
    arp_user = AppUser(
        id=uuid.uuid4(),
        username="arp.demo",
        role="arp",
        cluster_id="KNP-C01",
        password_hash="hash",
    )
    app = create_test_progress_app(session, user=arp_user)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/teacher/progress")
        assert res.status_code == 403


@pytest.mark.asyncio
async def test_get_progress_renders_evidence_ladder_scores_and_key_points() -> None:
    """GET /teacher/progress renders evidence ladder, scores, and covered key points correctly."""
    teacher_id = uuid.UUID("00000000-0000-0000-0000-000000000002")
    user_id = uuid.UUID("00000000-0000-0000-0001-000000000002")

    teacher = Teacher(
        id=teacher_id,
        name="अनीता देवी",
        preferred_channel="web",
        lite_mode=False,
        consent_share_scores=True,
        consent_research=False,
        is_demo=True,
    )
    user = AppUser(
        id=user_id,
        username="teacher.demo2",
        role="teacher",
        teacher_id=teacher_id,
        display_name="डेमो शिक्षिका 2 (अनीता)",
        password_hash="hash",
        is_demo=True,
    )

    move_id = "NUM_SUB_REGROUP_BUNDLES"
    move_path = MovePath(teacher_id=teacher_id, position=1, move_id=move_id)

    # Evidence level 3: levels 1, 2, 3 filled; 4, 5 unfilled
    evidence = AdoptionEvidence(
        id=uuid.uuid4(),
        teacher_id=teacher_id,
        move_id=move_id,
        level=3,
        source="peer_checklist",
    )

    # Rehearsal score: average 1.5/2 -> 75%
    rscore = RehearsalScore(
        id=uuid.uuid4(),
        teacher_id=teacher_id,
        move_id=move_id,
        attempt=1,
        scores={"wait_time": 2, "regroup_explanation": 1},
        evidence={},
    )

    # Explain score: kp1 covered, kp2 missing
    escore = ExplainScore(
        id=uuid.uuid4(),
        teacher_id=teacher_id,
        move_id=move_id,
        points={"kp1": "covered", "kp2": "missing"},
    )

    session = InMemoryProgressSession(entities=[teacher, user, move_path, evidence, rscore, escore])
    app = create_test_progress_app(session, user=user)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/teacher/progress")
        assert res.status_code == 200
        html = res.text

        # 1. Header & Title
        assert "मेरी प्रगति" in html
        assert "अनीता देवी" in html

        # 2. Evidence Ladder (5 steps, filled up to max level 3)
        assert "प्रमाण सीढ़ी (Evidence Ladder)" in html
        assert "अभ्यास किया" in html
        assert "स्वयं बताया" in html
        assert "साथी ने देखा" in html
        assert "ARP ने देखा" in html
        assert "बच्चों में सुधार" in html

        # Check filled vs unfilled classes
        assert 'title="स्तर 1: अभ्यास किया"' in html
        assert 'title="स्तर 3: साथी ने देखा"' in html
        assert 'title="स्तर 4: ARP ने देखा"' in html

        # 3. Rubric Score History (Inline bars)
        assert "अभ्यास अंक इतिहास (Rubric Scores)" in html
        assert "प्रयास 1" in html
        assert "1.5/2" in html
        assert "width: 75%;" in html

        # 4. Explain-back Key Points
        assert "अपने शब्दों में समझाना (Key Points Covered)" in html
        assert "kp-item covered" in html
        assert "✓" in html

        # 5. Consent toggles state
        assert 'id="consent_share_scores"' in html
        assert 'id="consent_research"' in html
        # consent_share_scores is True -> checked
        assert 'name="consent_share_scores"' in html
        # Deletion link
        assert 'href="/teacher/delete"' in html


@pytest.mark.asyncio
async def test_post_consent_toggles_and_creates_consent_log() -> None:
    """POST /teacher/consent updates teacher consent and logs to ConsentLog."""
    teacher_id = uuid.UUID("00000000-0000-0000-0000-000000000001")
    teacher = Teacher(
        id=teacher_id,
        name="सुमन शर्मा",
        consent_share_scores=False,
        consent_research=False,
        is_demo=True,
    )
    user = AppUser(
        id=uuid.uuid4(),
        username="teacher.demo1",
        role="teacher",
        teacher_id=teacher_id,
        password_hash="hash",
    )

    session = InMemoryProgressSession(entities=[teacher, user])
    app = create_test_progress_app(session, user=user)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Post to enable ARP sharing and research consent (Bearer token in test env bypasses CSRF)
        resp = await client.post(
            "/teacher/consent",
            data={"consent_share_scores": "true", "consent_research": "true"},
            headers={"Authorization": "Bearer test-token"},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        assert "/teacher/progress?saved=1" in resp.headers["location"]

        # Verify teacher record updated
        assert teacher.consent_share_scores is True
        assert teacher.consent_research is True

        # Verify ConsentLog entries created
        consent_logs = [obj for obj in session.added if isinstance(obj, ConsentLog)]
        assert len(consent_logs) >= 2
        share_log = next(log for log in consent_logs if log.field == "consent_share_scores")
        assert share_log.value is True
        assert share_log.teacher_id == teacher_id
        assert share_log.channel == "web"

        research_log = next(log for log in consent_logs if log.field == "consent_research")
        assert research_log.value is True

        # 2. Toggle ARP sharing back to false
        resp2 = await client.post(
            "/teacher/consent",
            data={"consent_research": "true"},  # consent_share_scores omitted (checkbox unchecked)
            headers={"Authorization": "Bearer test-token"},
            follow_redirects=False,
        )
        assert resp2.status_code == 303
        assert teacher.consent_share_scores is False
        assert teacher.consent_research is True

        # Verify new ConsentLog created with False value
        latest_share_log = [
            log
            for log in session.added
            if isinstance(log, ConsentLog) and log.field == "consent_share_scores"
        ][-1]
        assert latest_share_log.value is False


@pytest.mark.asyncio
async def test_get_delete_confirm_page() -> None:
    """GET /teacher/delete renders confirmation dialog page delete.html."""
    teacher_id = uuid.UUID("00000000-0000-0000-0000-000000000002")
    teacher = Teacher(id=teacher_id, name="अनीता देवी", is_demo=True)
    user = AppUser(
        id=uuid.uuid4(),
        username="teacher.demo2",
        role="teacher",
        teacher_id=teacher_id,
        password_hash="hash",
    )

    session = InMemoryProgressSession(entities=[teacher, user])
    app = create_test_progress_app(session, user=user)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/teacher/delete")
        assert res.status_code == 200
        html = res.text

        # Dialog heading & explanation
        assert "क्या आप वाकई अपना सारा डेटा हटाना चाहती हैं?" in html
        assert "स्थायी और अपरिवर्तनीय" in html

        # Confirmation button [हाँ, मिटाएँ]
        assert "हाँ, मिटाएँ" in html
        assert 'id="btn-confirm-delete"' in html

        # Cancel link [नहीं, वापस जाएँ]
        assert "नहीं, वापस जाएँ" in html
        assert 'href="/teacher/progress"' in html


@pytest.mark.asyncio
async def test_get_delete_confirm_page_uses_masculine_form_for_male_teacher() -> None:
    """fix3 B09: the confirmation question follows the teacher's address form."""
    teacher_id = uuid.UUID("00000000-0000-0000-0000-000000000009")
    teacher = Teacher(id=teacher_id, name="सुनील", is_demo=False, address_form="m")
    user = AppUser(
        id=uuid.uuid4(),
        username="teacher.m",
        role="teacher",
        teacher_id=teacher_id,
        password_hash="hash",
    )
    app = create_test_progress_app(InMemoryProgressSession(entities=[teacher, user]), user=user)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        html = (await client.get("/teacher/delete")).text
    assert "चाहते हैं?" in html
    assert "चाहती हैं" not in html


@pytest.mark.asyncio
async def test_post_delete_purges_data_and_logs_out() -> None:
    """POST /teacher/delete purges all teacher data and logs out with redirect to /login."""
    teacher_id = uuid.UUID("00000000-0000-0000-0000-000000000003")
    user_id = uuid.UUID("00000000-0000-0000-0001-000000000003")
    scene_id = uuid.uuid4()

    teacher = Teacher(id=teacher_id, name="रेखा कुमारी", is_demo=True)
    user = AppUser(
        id=user_id,
        username="teacher.real",
        role="teacher",
        teacher_id=teacher_id,
        password_hash="hash",
    )
    scene = Scene(id=scene_id, teacher_id=teacher_id, engine_state={})
    turn = Turn(id=uuid.uuid4(), teacher_id=teacher_id, scene_id=scene_id, role="teacher")
    rscore = RehearsalScore(
        id=uuid.uuid4(), teacher_id=teacher_id, scene_id=scene_id, scores={}, evidence={}
    )
    escore = ExplainScore(id=uuid.uuid4(), teacher_id=teacher_id, points={})
    evidence = AdoptionEvidence(
        id=uuid.uuid4(), teacher_id=teacher_id, move_id="M1", level=1, source="rehearsal"
    )
    sstate = SessionState(
        teacher_id=teacher_id, week_start=date(2026, 10, 12), move_id="M1", state="DONE"
    )
    mpath = MovePath(teacher_id=teacher_id, position=1, move_id="M1")
    msg = Message(
        id=uuid.uuid4(), teacher_id=teacher_id, direction="in", channel="web", channel_msg_id="m1"
    )
    clog = ConsentLog(id=uuid.uuid4(), teacher_id=teacher_id, field="share", value=True)
    question_id = uuid.uuid4()
    question = Question(
        id=question_id,
        teacher_id=teacher_id,
        text="बच्चों को घटाव कैसे सिखाएँ?",
        status="answered",
    )
    scheduled_job = ScheduledJob(
        id=uuid.uuid4(),
        kind="followup",
        run_at=datetime.now(UTC),
        payload={"teacher_id": str(teacher_id), "question_id": str(question_id)},
    )
    review_item = ReviewItem(
        id=uuid.uuid4(),
        kind="question",
        ref_id=str(question_id),
        status="open",
    )

    session = InMemoryProgressSession(
        entities=[
            teacher,
            user,
            scene,
            turn,
            rscore,
            escore,
            evidence,
            sstate,
            mpath,
            msg,
            clog,
            question,
            scheduled_job,
            review_item,
        ]
    )
    app = create_test_progress_app(session, user=user)

    # Issue a valid session cookie
    token = create_session_token({"user_id": str(user_id), "role": "teacher"})
    cookies = {SESSION_COOKIE_NAME: token}

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", cookies=cookies
    ) as client:
        resp = await client.post(
            "/teacher/delete",
            headers={"Authorization": "Bearer test-token"},
            follow_redirects=False,
        )
        # 1. Redirect to /login
        assert resp.status_code == 303
        assert resp.headers["location"] == "/login"

        # 2. Session cookie cleared
        set_cookie = resp.headers.get("set-cookie", "")
        assert (
            f'{SESSION_COOKIE_NAME}=""' in set_cookie
            or f"{SESSION_COOKIE_NAME}=;" in set_cookie
            or "max-age=0" in set_cookie.lower()
        )

        # 3. Data purged from database (including scheduled jobs and review items)
        assert teacher in session.deleted
        assert user in session.deleted
        assert scene in session.deleted
        assert turn in session.deleted
        assert rscore in session.deleted
        assert escore in session.deleted
        assert evidence in session.deleted
        assert sstate in session.deleted
        assert mpath in session.deleted
        assert msg in session.deleted
        assert clog in session.deleted
        assert question in session.deleted
        assert scheduled_job in session.deleted
        assert review_item in session.deleted
        assert len(session.entities) == 0


@pytest.mark.asyncio
async def test_post_delete_on_shared_demo_login_resets_instead_of_deleting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """fix3 B02: "delete my data" on teacher.demo1/2/3 resets the seeded state; the login survives."""
    import backend.app.db.seed as seed_mod
    import backend.app.web.teacher as teacher_mod

    teacher_id = uuid.UUID("00000000-0000-0000-0000-000000000001")
    user_id = uuid.UUID("00000000-0000-0000-0001-000000000001")
    teacher = Teacher(id=teacher_id, name="डेमो", is_demo=True)
    user = AppUser(
        id=user_id,
        username="teacher.demo1",
        role="teacher",
        teacher_id=teacher_id,
        password_hash="hash",
    )
    session = InMemoryProgressSession(entities=[teacher, user])
    app = create_test_progress_app(session, user=user)
    reset_calls: list[str] = []
    purge_calls: list[uuid.UUID] = []

    async def fake_reset(_db: Any, login: str) -> bool:
        reset_calls.append(login)
        return True

    async def fake_purge(_db: Any, tid: uuid.UUID) -> None:
        purge_calls.append(tid)

    monkeypatch.setattr(seed_mod, "reset_demo_teacher", fake_reset)
    monkeypatch.setattr(teacher_mod, "purge_teacher_data", fake_purge)
    token = create_session_token({"user_id": str(user_id), "role": "teacher"})

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        cookies={SESSION_COOKIE_NAME: token},
    ) as client:
        resp = await client.post(
            "/teacher/delete",
            headers={"Authorization": "Bearer test-token"},
            follow_redirects=False,
        )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login"
    assert reset_calls == ["teacher.demo1"]
    assert purge_calls == []
    assert teacher not in session.deleted
    assert user not in session.deleted


@pytest.mark.asyncio
async def test_post_delete_without_csrf_returns_403_and_purges_nothing() -> None:
    """POST /teacher/delete without CSRF token returns 403 and purges nothing."""
    teacher_id = uuid.UUID("00000000-0000-0000-0000-000000000004")
    user_id = uuid.UUID("00000000-0000-0000-0001-000000000004")

    teacher = Teacher(id=teacher_id, name="आरती", is_demo=True)
    user = AppUser(
        id=user_id,
        username="teacher.demo4",
        role="teacher",
        teacher_id=teacher_id,
        password_hash="hash",
    )
    session = InMemoryProgressSession(entities=[teacher, user])
    app = create_test_progress_app(session, user=user)

    token = create_session_token({"user_id": str(user_id), "role": "teacher"})
    cookies = {SESSION_COOKIE_NAME: token}

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", cookies=cookies
    ) as client:
        # Omits Authorization header and CSRF token/cookie -> verify_csrf_token must reject
        resp = await client.post("/teacher/delete", follow_redirects=False)
        assert resp.status_code == 403
        assert teacher not in session.deleted
        assert user not in session.deleted
        assert len(session.entities) == 2


@pytest.mark.asyncio
async def test_consent_uncheck_on_class_form_turns_sharing_off_and_writes_consent_log() -> None:
    """Unchecking consent on class form saves False and writes a ConsentLog row."""
    teacher_id = uuid.UUID("00000000-0000-0000-0000-000000000001")
    teacher = Teacher(
        id=teacher_id,
        name="सुमन शर्मा",
        consent_share_scores=True,
        consent_research=True,
        is_demo=True,
    )
    user = AppUser(
        id=uuid.uuid4(),
        username="teacher.demo1",
        role="teacher",
        teacher_id=teacher_id,
        password_hash="hash",
    )

    session = InMemoryProgressSession(entities=[teacher, user])
    app = create_test_progress_app(session, user=user)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Case A: Browser submits hidden false input because checkbox was unchecked
        resp = await client.post(
            "/teacher/consent",
            data={
                "form_source": "class",
                "redirect_to": "/teacher/class",
                "consent_share_scores": "false",
            },
            headers={"Authorization": "Bearer test-token"},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        assert resp.headers["location"] == "/teacher/class"
        assert teacher.consent_share_scores is False
        # Research consent must NOT be touched by class form
        assert teacher.consent_research is True

        # Verify ConsentLog entry created with value False
        logs = [
            obj
            for obj in session.added
            if isinstance(obj, ConsentLog) and obj.field == "consent_share_scores"
        ]
        assert len(logs) == 1
        assert logs[0].value is False
        assert logs[0].teacher_id == teacher_id
        assert logs[0].channel == "web"

        # Case B: Re-enable sharing, then uncheck where checkbox is omitted completely
        teacher.consent_share_scores = True
        resp2 = await client.post(
            "/teacher/consent",
            data={
                "form_source": "class",
                "redirect_to": "/teacher/class",
            },
            headers={"Authorization": "Bearer test-token"},
            follow_redirects=False,
        )
        assert resp2.status_code == 303
        assert resp2.headers["location"] == "/teacher/class"
        assert teacher.consent_share_scores is False
        latest_log = [
            obj
            for obj in session.added
            if isinstance(obj, ConsentLog) and obj.field == "consent_share_scores"
        ][-1]
        assert latest_log.value is False


@pytest.mark.asyncio
async def test_consent_uncheck_on_progress_form_turns_sharing_off_and_writes_consent_log() -> None:
    """Unchecking consent on progress form saves False and writes a ConsentLog row."""
    teacher_id = uuid.UUID("00000000-0000-0000-0000-000000000001")
    teacher = Teacher(
        id=teacher_id,
        name="सुमन शर्मा",
        consent_share_scores=True,
        consent_research=True,
        is_demo=True,
    )
    user = AppUser(
        id=uuid.uuid4(),
        username="teacher.demo1",
        role="teacher",
        teacher_id=teacher_id,
        password_hash="hash",
    )

    session = InMemoryProgressSession(entities=[teacher, user])
    app = create_test_progress_app(session, user=user)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Uncheck score sharing, keep research consent
        resp = await client.post(
            "/teacher/consent",
            data={
                "form_source": "progress",
                "redirect_to": "/teacher/progress?saved=1",
                "consent_share_scores": "false",
                "consent_research": "true",
            },
            headers={"Authorization": "Bearer test-token"},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        assert resp.headers["location"] == "/teacher/progress?saved=1"
        assert teacher.consent_share_scores is False
        assert teacher.consent_research is True

        share_log = next(
            log
            for log in session.added
            if isinstance(log, ConsentLog) and log.field == "consent_share_scores"
        )
        assert share_log.value is False

        # Uncheck BOTH
        teacher.consent_share_scores = True
        resp2 = await client.post(
            "/teacher/consent",
            data={
                "form_source": "progress",
                "redirect_to": "/teacher/progress?saved=1",
                "consent_share_scores": "false",
                "consent_research": "false",
            },
            headers={"Authorization": "Bearer test-token"},
            follow_redirects=False,
        )
        assert resp2.status_code == 303
        assert teacher.consent_share_scores is False
        assert teacher.consent_research is False

        latest_share = [
            log
            for log in session.added
            if isinstance(log, ConsentLog) and log.field == "consent_share_scores"
        ][-1]
        assert latest_share.value is False

        latest_research = [
            log
            for log in session.added
            if isinstance(log, ConsentLog) and log.field == "consent_research"
        ][-1]
        assert latest_research.value is False


@pytest.mark.asyncio
async def test_consent_redirect_restriction() -> None:
    """Restricts redirect_to to local paths starting with a single '/' and rejects '//', schemes, backslashes."""
    teacher_id = uuid.UUID("00000000-0000-0000-0000-000000000001")
    teacher = Teacher(id=teacher_id, name="सुमन शर्मा", is_demo=True)
    user = AppUser(
        id=uuid.uuid4(),
        username="teacher.demo1",
        role="teacher",
        teacher_id=teacher_id,
        password_hash="hash",
    )

    session = InMemoryProgressSession(entities=[teacher, user])
    app = create_test_progress_app(session, user=user)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Valid local paths
        for path in ["/teacher/class", "/teacher/progress?saved=1", "/teacher"]:
            res = await client.post(
                "/teacher/consent",
                data={"redirect_to": path, "consent_share_scores": "true"},
                headers={"Authorization": "Bearer test-token"},
                follow_redirects=False,
            )
            assert res.status_code == 303
            assert res.headers["location"] == path

        # Dangerous/open redirects that MUST be rejected and default to /teacher/progress?saved=1
        invalid_redirects = [
            "//evil.com",
            "///evil.com",
            "https://evil.com/phish",
            "http://evil.com",
            "javascript:alert(1)",
            r"\evil.com",
            r"/\evil.com",
            r"/teacher\class",
            "ftp://files.example.com",
            "",
            "   ",
        ]
        for bad_url in invalid_redirects:
            res = await client.post(
                "/teacher/consent",
                data={"redirect_to": bad_url, "consent_share_scores": "true"},
                headers={"Authorization": "Bearer test-token"},
                follow_redirects=False,
            )
            assert res.status_code == 303
            assert res.headers["location"] == "/teacher/progress?saved=1", f"Failed for {bad_url}"


@pytest.mark.asyncio
async def test_score_history_numbers_attempts_in_order_even_if_stored_attempts_repeat() -> None:
    """fix5: two stored rows with attempt=1 must not both read 'Attempt 1'."""
    teacher_id = uuid.UUID("00000000-0000-0000-0000-000000000003")
    teacher = Teacher(
        id=teacher_id,
        name="अनीता देवी",
        preferred_channel="web",
        lite_mode=False,
        consent_share_scores=True,
        consent_research=False,
        is_demo=True,
    )
    user = AppUser(
        id=uuid.UUID("00000000-0000-0000-0001-000000000003"),
        username="teacher.demo3",
        role="teacher",
        teacher_id=teacher_id,
        display_name="डेमो",
        password_hash="hash",
        is_demo=True,
    )
    move_id = "NUM_SUB_REGROUP_BUNDLES"
    rows = [
        RehearsalScore(
            id=uuid.uuid4(),
            teacher_id=teacher_id,
            move_id=move_id,
            attempt=a,
            scores={"wait_time": s, "regroup_explanation": s},
            evidence={},
        )
        for a, s in ((1, 1), (1, 0), (2, 2))
    ]
    session = InMemoryProgressSession(
        entities=[
            teacher,
            user,
            MovePath(teacher_id=teacher_id, position=1, move_id=move_id),
            *rows,
        ]
    )
    app = create_test_progress_app(session, user=user)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        html = (await client.get("/teacher/progress")).text
    for n in (1, 2, 3):
        assert html.count(f"प्रयास {n}") == 1
