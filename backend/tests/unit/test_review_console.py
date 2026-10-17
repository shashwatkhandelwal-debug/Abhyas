"""Unit tests for Coach Review Console and Calibration (spec/09 §9.5, T34)."""

from __future__ import annotations

import json
import uuid
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from backend.app.auth.csrf import CSRF_COOKIE_NAME, generate_csrf_token
from backend.app.auth.guards import get_current_user
from backend.app.db.models import (
    AppUser,
    CalibrationLabel,
    ContentRelease,
    Move,
    RehearsalScore,
    ReviewItem,
    Scene,
    Turn,
)
from backend.app.db.session import get_db_session
from backend.app.main import app


class FakeAsyncSession:
    """In-memory mock session supporting basic queries for review console unit testing."""

    def __init__(self) -> None:
        self.items: dict[type, list[Any]] = {
            ReviewItem: [],
            CalibrationLabel: [],
            Scene: [],
            Turn: [],
            RehearsalScore: [],
            Move: [],
            ContentRelease: [ContentRelease(id="rel-seed-v1", is_active=True)],
        }
        self.committed = False

    def add(self, obj: Any) -> None:
        obj_type = type(obj)
        if obj_type not in self.items:
            self.items[obj_type] = []
        if getattr(obj, "id", None) is None:
            if hasattr(obj, "id"):
                obj.id = uuid.uuid4()
        self.items[obj_type].append(obj)

    async def get(self, model: type, ident: Any) -> Any | None:
        for obj in self.items.get(model, []):
            if getattr(obj, "id", None) == ident:
                return obj
        return None

    async def execute(self, stmt: Any) -> Any:
        class FakeResult:
            def __init__(self, data: list[Any]) -> None:
                self._data = data

            def scalars(self) -> FakeResult:
                return self

            def all(self) -> list[Any]:
                return list(self._data)

            def scalar_one_or_none(self) -> Any | None:
                return self._data[0] if self._data else None

            def first(self) -> Any | None:
                return self._data[0] if self._data else None

            def scalar(self) -> Any:
                return len(self._data)

        # Basic filtering by model
        stmt_str = str(stmt)
        if "FROM review_item" in stmt_str or "review_item" in stmt_str:
            data = list(self.items.get(ReviewItem, []))
            if "status = :status_1" in stmt_str or "status = 'open'" in stmt_str:
                data = [x for x in data if getattr(x, "status", None) == "open"]
            return FakeResult(data)
        if "FROM move" in stmt_str or "move." in stmt_str:
            data = list(self.items.get(Move, []))
            return FakeResult(data)
        if "FROM turn" in stmt_str:
            return FakeResult(list(self.items.get(Turn, [])))
        if "FROM scene" in stmt_str:
            data = list(self.items.get(Scene, []))
            if "status = :status_1" in stmt_str or "status = 'ended'" in stmt_str:
                data = [x for x in data if getattr(x, "status", None) == "ended"]
            if "NOT IN" in stmt_str or "not_in" in stmt_str:
                labelled_ids = {
                    getattr(c, "scene_id", None)
                    for c in self.items.get(CalibrationLabel, [])
                    if getattr(c, "blind", False)
                }
                data = [x for x in data if getattr(x, "id", None) not in labelled_ids]
            return FakeResult(data)
        if "FROM rehearsal_score" in stmt_str:
            return FakeResult(list(self.items.get(RehearsalScore, [])))
        if "FROM calibration_label" in stmt_str:
            return FakeResult(list(self.items.get(CalibrationLabel, [])))

        return FakeResult([])

    async def flush(self) -> None:
        pass

    async def commit(self) -> None:
        self.committed = True


def _make_coach_user(username: str = "coach.demo", role: str = "coach") -> AppUser:
    return AppUser(
        id=uuid.uuid4(),
        username=username,
        password_hash="fake_hash",
        role=role,
        display_name=f"Demo {role.capitalize()}",
        is_demo=True,
    )


@pytest.mark.asyncio
async def test_review_role_authorization() -> None:
    """Verifies that only coach and admin can access review console routes (§9.7)."""
    fake_session = FakeAsyncSession()

    async def override_db() -> Any:
        return fake_session

    app.dependency_overrides[get_db_session] = override_db

    # 1. Teacher cannot access review (403)
    teacher_user = _make_coach_user("teacher.demo1", role="teacher")
    app.dependency_overrides[get_current_user] = lambda: teacher_user

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        res = await client.get("/review")
        assert res.status_code == 403

    # 2. ARP cannot access review (403)
    arp_user = _make_coach_user("arp.demo", role="arp")
    app.dependency_overrides[get_current_user] = lambda: arp_user

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        res = await client.get("/review")
        assert res.status_code == 403

    # 3. Coach CAN access review (200)
    coach_user = _make_coach_user("coach.demo", role="coach")
    app.dependency_overrides[get_current_user] = lambda: coach_user

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        res = await client.get("/review")
        assert res.status_code == 200
        assert "कोच समीक्षा कंसोल" in res.text

    # 4. Admin CAN access review (200)
    admin_user = _make_coach_user("admin.demo", role="admin")
    app.dependency_overrides[get_current_user] = lambda: admin_user

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        res = await client.get("/review")
        assert res.status_code == 200

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_review_dashboard_tabs_and_items() -> None:
    """Tests queue tabs rendering and review items listing (§9.5)."""
    fake_session = FakeAsyncSession()

    # Seed an open review item
    item_id = uuid.uuid4()
    item = ReviewItem(
        id=item_id,
        kind="rehearsal_score",
        ref_id=str(uuid.uuid4()),
        reason="कम भरोसा (0.55 < 0.70)",
        status="open",
        created_at=None,
    )
    fake_session.items[ReviewItem].append(item)

    coach_user = _make_coach_user("coach.demo", role="coach")
    app.dependency_overrides[get_db_session] = lambda: fake_session
    app.dependency_overrides[get_current_user] = lambda: coach_user

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # Default tab = scores
        res = await client.get("/review")
        assert res.status_code == 200
        assert "कम भरोसा" in res.text
        assert "0.55" in res.text
        assert f"/review/items/{item_id}" in res.text

        # Questions tab
        res_q = await client.get("/review?tab=questions")
        assert res_q.status_code == 200

        # Moves tab
        res_m = await client.get("/review?tab=moves")
        assert res_m.status_code == 200
        assert "मूव कोड" in res_m.text

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_rehearsal_review_item_detail_and_resolve() -> None:
    """Tests loading rehearsal review detail with transcript and resolving with coach scores (§9.5)."""
    fake_session = FakeAsyncSession()

    teacher_id = uuid.uuid4()
    scene_id = uuid.uuid4()
    scene = Scene(
        id=scene_id,
        teacher_id=teacher_id,
        move_id="NUM_SUB_REGROUP_BUNDLES",
        status="ended",
        mode="normal",
        engine_state={},
    )
    fake_session.items[Scene].append(scene)

    turn1 = Turn(
        id=uuid.uuid4(),
        teacher_id=teacher_id,
        scene_id=scene_id,
        idx=0,
        role="teacher",
        transcript="रवि, तुम्हारे पास कितने बंडल हैं?",
        acts=["ASK_CHILD"],
    )
    turn2 = Turn(
        id=uuid.uuid4(),
        teacher_id=teacher_id,
        scene_id=scene_id,
        idx=1,
        role="ravi",
        transcript="मेरे पास 3 बंडल और 2 तीलियाँ हैं।",
        acts=[],
    )
    fake_session.items[Turn].extend([turn1, turn2])

    r_score = RehearsalScore(
        id=uuid.uuid4(),
        teacher_id=uuid.uuid4(),
        scene_id=scene_id,
        move_id="NUM_SUB_REGROUP_BUNDLES",
        scores={"accuracy": 1, "bundle_opening": 0},
        evidence={"accuracy": "रवि, तुम्हारे पास कितने बंडल हैं?"},
        confidence=0.58,
        needs_review=True,
    )
    fake_session.items[RehearsalScore].append(r_score)

    item_id = uuid.uuid4()
    item = ReviewItem(
        id=item_id,
        kind="rehearsal_score",
        ref_id=str(scene_id),
        reason="कम भरोसा (0.58 < 0.70)",
        status="open",
    )
    fake_session.items[ReviewItem].append(item)

    coach_user = _make_coach_user("coach.demo", role="coach")
    app.dependency_overrides[get_db_session] = lambda: fake_session
    app.dependency_overrides[get_current_user] = lambda: coach_user

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # 1. GET Detail Page
        res_detail = await client.get(f"/review/items/{item_id}")
        assert res_detail.status_code == 200
        html = res_detail.text
        assert "रवि, तुम्हारे पास कितने बंडल हैं?" in html
        assert "ASK_CHILD" in html
        assert "0.58" in html
        assert ('name="score_crit_explain"' in html) or ('name="score_accuracy"' in html)

        # 2. POST Resolve
        token = generate_csrf_token()
        client.cookies.set(CSRF_COOKIE_NAME, token)

        post_data = {
            "csrf_token": token,
            "score_crit_explain": "2",
            "score_crit_concrete": "1",
            "score_accuracy": "2",
            "score_bundle_opening": "1",
            "note": "शिक्षक ने स्पष्ट रूप से प्रश्न पूछा।",
        }
        res_resolve = await client.post(
            f"/review/items/{item_id}/resolve",
            data=post_data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            follow_redirects=False,
        )
        assert res_resolve.status_code == 303
        assert "/review?tab=scores&success=1" in res_resolve.headers["location"]

        # Item must now be resolved
        assert item.status == "resolved"
        assert item.resolved_by == coach_user.id
        assert item.resolution is not None
        assert item.resolution["note"] == "शिक्षक ने स्पष्ट रूप से प्रश्न पूछा।"

        # CalibrationLabel must be added (blind=False)
        calibs = fake_session.items[CalibrationLabel]
        assert len(calibs) == 1
        assert calibs[0].scene_id == scene_id
        assert calibs[0].coach_user_id == coach_user.id
        assert calibs[0].blind is False
        assert calibs[0].scores.get("crit_explain", calibs[0].scores.get("accuracy")) == 2

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_blind_calibration_mode_and_export() -> None:
    """Tests blind double-coding mode without AI scores and JSONL export (§9.5)."""
    fake_session = FakeAsyncSession()

    teacher_id = uuid.uuid4()
    scene_id = uuid.uuid4()
    scene = Scene(
        id=scene_id,
        teacher_id=teacher_id,
        move_id="NUM_SUB_REGROUP_BUNDLES",
        status="ended",
        mode="normal",
        engine_state={},
    )
    fake_session.items[Scene].append(scene)

    turn = Turn(
        id=uuid.uuid4(),
        teacher_id=teacher_id,
        scene_id=scene_id,
        idx=0,
        role="teacher",
        transcript="आओ पहले बंडल खोलें।",
        acts=["EXPLAIN"],
    )
    fake_session.items[Turn].append(turn)

    coach_user = _make_coach_user("coach.demo", role="coach")
    app.dependency_overrides[get_db_session] = lambda: fake_session
    app.dependency_overrides[get_current_user] = lambda: coach_user

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # 1. GET /review/calibrate: Renders transcript WITHOUT AI scores
        res_calib = await client.get(f"/review/calibrate?scene_id={scene_id}")
        assert res_calib.status_code == 200
        html = res_calib.text
        assert "ब्लाइंड कैलिब्रेशन मोड" in html
        assert "आओ पहले बंडल खोलें।" in html
        # MUST NOT leak internal act tag or AI scores
        assert "EXPLAIN" not in html
        assert "AI द्वारा दिया गया स्कोर" not in html

        # 2. POST /review/calibrate
        token = generate_csrf_token()
        client.cookies.set(CSRF_COOKIE_NAME, token)

        post_data = {
            "csrf_token": token,
            "scene_id": str(scene_id),
            "score_crit_explain": "2",
            "score_crit_concrete": "2",
            "note": "ब्लाइंड मूल्यांकन पूरा हुआ।",
        }
        res_post = await client.post(
            "/review/calibrate",
            data=post_data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            follow_redirects=False,
        )
        assert res_post.status_code == 303
        assert "/review/calibrate?success=1" in res_post.headers["location"]

        calibs = fake_session.items[CalibrationLabel]
        assert len(calibs) == 1
        assert calibs[0].blind is True
        assert calibs[0].scores == {"crit_explain": 2, "crit_concrete": 2}

        # 3. GET /review/calibration.jsonl
        res_jsonl = await client.get("/review/calibration.jsonl")
        assert res_jsonl.status_code == 200
        assert "application/x-ndjson" in res_jsonl.headers["content-type"]
        line = res_jsonl.text.strip().splitlines()[0]
        data = json.loads(line)
        assert data["scene_id"] == str(scene_id)
        assert data["coach_user_id"] == str(coach_user.id)
        assert data["blind"] is True
        assert data["scores"] == {"crit_explain": 2, "crit_concrete": 2}

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_blind_calibration_rejects_unknown_criterion_with_400() -> None:
    """POST /review/calibrate rejects unknown score criteria with 400."""
    fake_session = FakeAsyncSession()
    scene_id = uuid.uuid4()
    scene = Scene(
        id=scene_id,
        teacher_id=uuid.uuid4(),
        move_id="NUM_SUB_REGROUP_BUNDLES",
        status="ended",
        mode="normal",
        engine_state={},
    )
    fake_session.items[Scene].append(scene)

    coach_user = _make_coach_user("coach.demo", role="coach")
    app.dependency_overrides[get_db_session] = lambda: fake_session
    app.dependency_overrides[get_current_user] = lambda: coach_user

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        token = generate_csrf_token()
        client.cookies.set(CSRF_COOKIE_NAME, token)

        post_data = {
            "csrf_token": token,
            "scene_id": str(scene_id),
            "score_unknown_crit": "2",
        }
        res = await client.post(
            "/review/calibrate",
            data=post_data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert res.status_code == 400
        assert "Unknown rubric criterion" in res.text

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_move_review_and_two_coach_approval() -> None:
    """Tests move review, raw YAML validation, and 2 distinct coach approvals requirement (§9.5)."""
    fake_session = FakeAsyncSession()

    move_id = "NUM_SUB_REGROUP_BUNDLES"
    move = Move(
        id=move_id,
        release_id="rel-seed-v1",
        domain="math",
        title_hi="दो अंकों की हासिल वाली घटाव",
        sankul_month="10",
        status="in_review",
        payload={"id": move_id, "title_hi": "दो अंकों की हासिल वाली घटाव"},
        approvals=[],
    )
    fake_session.items[Move].append(move)

    coach1 = _make_coach_user("coach.demo", role="coach")
    coach2 = _make_coach_user("admin.demo", role="admin")

    app.dependency_overrides[get_db_session] = lambda: fake_session
    app.dependency_overrides[get_current_user] = lambda: coach1

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # 1. GET /review/moves/{move_id}
        res_move = await client.get(f"/review/moves/{move_id}")
        assert res_move.status_code == 200
        assert "दो अंकों की हासिल वाली घटाव" in res_move.text
        assert "0 / 2" in res_move.text

        # 2. First coach approves
        token = generate_csrf_token()
        client.cookies.set(CSRF_COOKIE_NAME, token)

        res_appr1 = await client.post(
            f"/review/moves/{move_id}/approve",
            data={"csrf_token": token},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            follow_redirects=False,
        )
        assert res_appr1.status_code == 303
        assert len(move.approvals) == 1
        assert move.status == "in_review"  # 1 approval is not enough

        # Duplicate approval by same coach does not increase count
        res_appr1_dup = await client.post(
            f"/review/moves/{move_id}/approve",
            data={"csrf_token": token},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            follow_redirects=False,
        )
        assert res_appr1_dup.status_code == 303
        assert len(move.approvals) == 1
        assert move.status == "in_review"

        # 3. Second distinct coach approves
        app.dependency_overrides[get_current_user] = lambda: coach2
        token2 = generate_csrf_token()
        client.cookies.set(CSRF_COOKIE_NAME, token2)

        res_appr2 = await client.post(
            f"/review/moves/{move_id}/approve",
            data={"csrf_token": token2},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            follow_redirects=False,
        )
        assert res_appr2.status_code == 303
        assert len(move.approvals) == 2
        # Now approved because distinct approvers == 2!
        assert move.status == "approved"

        # 4. YAML Schema Validation API
        from pathlib import Path

        valid_yaml = (Path("content/moves/NUM_SUB_REGROUP_BUNDLES.yaml")).read_text(
            encoding="utf-8"
        )
        res_val = await client.post(
            f"/review/moves/{move_id}/validate-yaml",
            json={"yaml_content": valid_yaml},
            headers={"x-csrf-token": token2},
        )
        assert res_val.status_code == 200
        val_json = res_val.json()
        assert val_json["valid"] is True
        assert val_json["criteria_count"] == 4

        # Invalid YAML
        res_inval = await client.post(
            f"/review/moves/{move_id}/validate-yaml",
            json={"yaml_content": "invalid: [missing required fields]"},
            headers={"x-csrf-token": token2},
        )
        assert res_inval.status_code == 200
        assert res_inval.json()["valid"] is False

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_validate_move_yaml_requires_csrf() -> None:
    """POST /review/moves/{id}/validate-yaml without CSRF token must return 403 Forbidden."""
    fake_session = FakeAsyncSession()
    coach = _make_coach_user("coach.demo", role="coach")
    app.dependency_overrides[get_db_session] = lambda: fake_session
    app.dependency_overrides[get_current_user] = lambda: coach

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        res = await client.post(
            "/review/moves/NUM_SUB_REGROUP_BUNDLES/validate-yaml",
            json={"yaml_content": "id: test"},
        )
        assert res.status_code == 403

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_blind_calibration_duplicate_post_rejected_with_409() -> None:
    """Duplicate blind calibration POST for same (coach, scene) must return 409 Conflict."""
    fake_session = FakeAsyncSession()
    scene_id = uuid.uuid4()
    scene = Scene(
        id=scene_id,
        teacher_id=uuid.uuid4(),
        move_id="NUM_SUB_REGROUP_BUNDLES",
        status="ended",
        mode="normal",
        engine_state={},
    )
    fake_session.items[Scene].append(scene)

    coach = _make_coach_user("coach.demo", role="coach")
    app.dependency_overrides[get_db_session] = lambda: fake_session
    app.dependency_overrides[get_current_user] = lambda: coach

    token = generate_csrf_token()
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://testserver",
        cookies={CSRF_COOKIE_NAME: token},
    ) as client:
        post_data = {
            "csrf_token": token,
            "scene_id": str(scene_id),
            "score_crit_explain": "2",
        }
        # First submission succeeds (303 redirect)
        res1 = await client.post(
            "/review/calibrate",
            data=post_data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            follow_redirects=False,
        )
        assert res1.status_code == 303

        # Second submission by same coach on same scene returns 409 Conflict
        res2 = await client.post(
            "/review/calibrate",
            data=post_data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            follow_redirects=False,
        )
        assert res2.status_code == 409
        assert "already exists" in res2.json()["detail"]
        assert len(fake_session.items[CalibrationLabel]) == 1

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_blind_calibration_refuses_scene_without_move_or_rubric() -> None:
    """A scene without valid move or rubric criteria refuses POST and renders empty state on GET."""
    fake_session = FakeAsyncSession()
    scene_id = uuid.uuid4()
    scene_no_move = Scene(
        id=scene_id,
        teacher_id=uuid.uuid4(),
        move_id="UNKNOWN_MOVE_NO_RUBRIC",
        status="ended",
        mode="normal",
        engine_state={},
    )
    fake_session.items[Scene].append(scene_no_move)

    coach = _make_coach_user("coach.demo", role="coach")
    app.dependency_overrides[get_db_session] = lambda: fake_session
    app.dependency_overrides[get_current_user] = lambda: coach

    token = generate_csrf_token()
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://testserver",
        cookies={CSRF_COOKIE_NAME: token},
    ) as client:
        # GET renders empty state because move rubric is missing
        res_get = await client.get(f"/review/calibrate?scene_id={scene_id}")
        assert res_get.status_code == 200
        assert "सभी उपलब्ध रिहर्सल जांची जा चुकी हैं" in res_get.text

        # POST is refused with 400 Bad Request
        res_post = await client.post(
            "/review/calibrate",
            data={"csrf_token": token, "scene_id": str(scene_id)},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            follow_redirects=False,
        )
        assert res_post.status_code == 400
        assert "rubric criteria missing" in res_post.json()["detail"]
        assert len(fake_session.items[CalibrationLabel]) == 0

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_blind_calibration_all_labelled_renders_empty_state() -> None:
    """When all ended scenes have been labelled with blind=True, GET /review/calibrate renders empty state."""
    fake_session = FakeAsyncSession()
    coach = _make_coach_user("coach.demo", role="coach")
    scene_id = uuid.uuid4()
    scene = Scene(
        id=scene_id,
        teacher_id=uuid.uuid4(),
        move_id="NUM_SUB_REGROUP_BUNDLES",
        status="ended",
        mode="normal",
        engine_state={},
    )
    fake_session.items[Scene].append(scene)

    # Label the scene
    label = CalibrationLabel(
        id=uuid.uuid4(),
        scene_id=scene_id,
        coach_user_id=coach.id,
        scores={"accuracy": 2},
        blind=True,
    )
    fake_session.items[CalibrationLabel].append(label)

    app.dependency_overrides[get_db_session] = lambda: fake_session
    app.dependency_overrides[get_current_user] = lambda: coach

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        res = await client.get("/review/calibrate")
        assert res.status_code == 200
        assert "सभी उपलब्ध रिहर्सल जांची जा चुकी हैं" in res.text

    app.dependency_overrides.clear()
