"""Integration tests for Coach Review Console and Calibration against real PostgreSQL (spec/09 §9.5, T34).

Skipped locally if TEST_DATABASE_URL is not set; runs in CI with real PostgreSQL+pgvector.
"""

from __future__ import annotations

import json
import os
import uuid
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from backend.app.auth.csrf import CSRF_COOKIE_NAME, generate_csrf_token
from backend.app.auth.guards import get_current_user
from backend.app.db.models import (
    AppUser,
    Base,
    RehearsalScore,
    ReviewItem,
    Scene,
    Teacher,
    Turn,
)
from backend.app.db.session import get_db_session
from backend.app.main import app

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL not set (runs in CI with real pgvector/pgvector:pg16)",
)


def _async_url(url: str) -> str:
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if "postgresql+psycopg2://" in url:
        return url.replace("postgresql+psycopg2://", "postgresql+asyncpg://")
    return url


@pytest.fixture
async def db_session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    assert TEST_DATABASE_URL is not None
    engine = create_async_engine(_async_url(TEST_DATABASE_URL), poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    yield maker
    await engine.dispose()


@pytest.mark.asyncio
async def test_review_console_postgres_end_to_end(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Verifies full review queue, detail, resolution, blind calibration, and move approvals on PostgreSQL."""
    async with db_session_factory() as session:
        # 1. Seed coach and admin users
        coach_user = AppUser(
            id=uuid.uuid4(),
            username=f"coach_test_{uuid.uuid4().hex[:6]}",
            password_hash="fake",
            role="coach",
            display_name="परीक्षण कोच",
            is_demo=True,
        )
        admin_user = AppUser(
            id=uuid.uuid4(),
            username=f"admin_test_{uuid.uuid4().hex[:6]}",
            password_hash="fake",
            role="admin",
            display_name="परीक्षण एडमिन",
            is_demo=True,
        )
        teacher = Teacher(
            id=uuid.uuid4(),
            name="अनिता वर्मा",
            school_id="SCH-001",
            district="Kanpur Nagar",
            is_demo=True,
        )
        session.add_all([coach_user, admin_user, teacher])
        await session.flush()

        # 2. Seed scene and turns
        scene_id = uuid.uuid4()
        scene = Scene(
            id=scene_id,
            teacher_id=teacher.id,
            move_id="NUM_SUB_REGROUP_BUNDLES",
            status="ended",
            mode="normal",
            engine_state={},
        )
        session.add(scene)
        await session.flush()

        turn1 = Turn(
            id=uuid.uuid4(),
            teacher_id=teacher.id,
            scene_id=scene_id,
            idx=0,
            role="teacher",
            transcript="रवि, 43 में से 27 कैसे घटाओगे?",
            acts=["ASK_CHILD"],
        )
        turn2 = Turn(
            id=uuid.uuid4(),
            teacher_id=teacher.id,
            scene_id=scene_id,
            idx=1,
            role="ravi",
            transcript="पहले खुली तीलियों से 7 घटाएँगे।",
            acts=[],
        )
        session.add_all([turn1, turn2])

        # 3. Seed RehearsalScore and ReviewItem
        r_score = RehearsalScore(
            id=uuid.uuid4(),
            teacher_id=teacher.id,
            scene_id=scene_id,
            move_id="NUM_SUB_REGROUP_BUNDLES",
            scores={"crit_explain": 1, "crit_concrete": 0},
            evidence={"crit_explain": "रवि, 43 में से 27 कैसे घटाओगे?"},
            confidence=0.52,
            needs_review=True,
        )
        session.add(r_score)
        await session.flush()

        item_id = uuid.uuid4()
        item = ReviewItem(
            id=item_id,
            kind="rehearsal_score",
            ref_id=str(scene_id),
            reason="स्कोर कम भरोसा (0.52 < 0.70)",
            status="open",
        )
        session.add(item)
        await session.commit()

    async def override_db() -> AsyncIterator[AsyncSession]:
        async with db_session_factory() as s:
            yield s

    async def override_user() -> AppUser:
        return coach_user

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_current_user] = override_user

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # 1. Test GET /review
        res_dash = await client.get("/review")
        assert res_dash.status_code == 200
        html = res_dash.text
        assert "कम भरोसा" in html
        assert f"/review/items/{item_id}" in html

        # 2. Test GET /review/items/{item_id}
        res_detail = await client.get(f"/review/items/{item_id}")
        assert res_detail.status_code == 200
        detail_html = res_detail.text
        assert "रवि, 43 में से 27 कैसे घटाओगे?" in detail_html
        assert "ASK_CHILD" in detail_html
        assert "0.52" in detail_html

        # 3. Test POST /review/items/{item_id}/resolve
        token = generate_csrf_token()
        client.cookies.set(CSRF_COOKIE_NAME, token)

        res_resolve = await client.post(
            f"/review/items/{item_id}/resolve",
            data={
                "csrf_token": token,
                "score_crit_explain": "2",
                "score_crit_concrete": "1",
                "note": "शिक्षक ने स्पष्ट रूप से तरीका पूछा।",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            follow_redirects=False,
        )
        assert res_resolve.status_code == 303

        # Verify in database: ReviewItem resolved and CalibrationLabel added
        async with db_session_factory() as verify_session:
            updated_item = await verify_session.get(ReviewItem, item_id)
            assert updated_item is not None
            assert updated_item.status == "resolved"
            assert updated_item.resolved_by == coach_user.id
            assert updated_item.resolution["scores"] == {"crit_explain": 2, "crit_concrete": 1}

            calib_stmt = text(
                "SELECT scene_id, coach_user_id, blind, scores, note FROM calibration_label WHERE scene_id = :sid"
            )
            calib_row = (await verify_session.execute(calib_stmt, {"sid": scene_id})).first()
            assert calib_row is not None
            assert calib_row.blind is False
            assert calib_row.coach_user_id == coach_user.id
            assert calib_row.scores == {"crit_explain": 2, "crit_concrete": 1}

        # 4. Test Blind Double-Coding Mode (GET /review/calibrate & POST /review/calibrate)
        res_calib = await client.get(f"/review/calibrate?scene_id={scene_id}")
        assert res_calib.status_code == 200
        assert "ब्लाइंड कैलिब्रेशन मोड" in res_calib.text
        assert "रवि, 43 में से 27 कैसे घटाओगे?" in res_calib.text
        # No internal tags or AI scores leaked
        assert "ASK_CHILD" not in res_calib.text
        assert "0.52" not in res_calib.text

        token_calib = generate_csrf_token()
        client.cookies.set(CSRF_COOKIE_NAME, token_calib)

        res_calib_post = await client.post(
            "/review/calibrate",
            data={
                "csrf_token": token_calib,
                "scene_id": str(scene_id),
                "score_crit_explain": "2",
                "score_crit_concrete": "2",
                "note": "ब्लाइंड डबल-कोडिंग पूर्ण",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            follow_redirects=False,
        )
        assert res_calib_post.status_code == 303

        # 5. Test JSONL Export (GET /review/calibration.jsonl)
        res_jsonl = await client.get("/review/calibration.jsonl")
        assert res_jsonl.status_code == 200
        assert "application/x-ndjson" in res_jsonl.headers["content-type"]
        lines = [json.loads(line) for line in res_jsonl.text.strip().splitlines() if line]
        assert len(lines) >= 2  # One from resolve, one from blind calibration
        blind_entry = next(e for e in lines if e.get("blind") is True)
        assert blind_entry["scene_id"] == str(scene_id)
        assert blind_entry["scores"] == {"crit_explain": 2, "crit_concrete": 2}

        # 6. Test Move Review and 2-Coach Approvals
        res_move_view = await client.get("/review/moves/NUM_SUB_REGROUP_BUNDLES")
        assert res_move_view.status_code == 200
        assert "NUM_SUB_REGROUP_BUNDLES" in res_move_view.text

        # Coach 1 approves
        token_appr1 = generate_csrf_token()
        client.cookies.set(CSRF_COOKIE_NAME, token_appr1)
        res_appr1 = await client.post(
            "/review/moves/NUM_SUB_REGROUP_BUNDLES/approve",
            data={"csrf_token": token_appr1},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            follow_redirects=False,
        )
        assert res_appr1.status_code == 303

        # Coach 2 (admin) approves
        app.dependency_overrides[get_current_user] = lambda: admin_user
        token_appr2 = generate_csrf_token()
        client.cookies.set(CSRF_COOKIE_NAME, token_appr2)
        res_appr2 = await client.post(
            "/review/moves/NUM_SUB_REGROUP_BUNDLES/approve",
            data={"csrf_token": token_appr2},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            follow_redirects=False,
        )
        assert res_appr2.status_code == 303

        # Verify in database: move now approved by 2 distinct coaches
        async with db_session_factory() as verify_session:
            stmt_move = text(
                "SELECT status, approvals FROM move WHERE id = 'NUM_SUB_REGROUP_BUNDLES'"
            )
            move_row = (await verify_session.execute(stmt_move)).first()
            assert move_row is not None
            assert move_row.status == "approved"
            approvals = move_row.approvals
            assert len(approvals) == 2

    app.dependency_overrides.clear()
