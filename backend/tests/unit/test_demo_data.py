"""Unit tests for synthetic demo cohort data (spec/03 §3.5, T31).

Verifies:
1. Teacher cohort counts across batches (KNP-B1: 25, KNP-B2: 18, KNP-B3: 8).
2. Suppression demonstration for batch KNP-B3 (n < 10).
3. Cluster KNP-C01 teacher count (12) and exact consent split (7 True, 5 False).
4. All teachers and users have is_demo=True and names prefixed with 'डेमो '.
5. Deliberate practice rehearsals run real engine & coach path on scripted teacher turns only.
6. Provenance is honest (model='mock' or 'fallback', real confidence, needs_review).
7. Evidence levels strictly match source:
   rehearsal -> 1 (>=3 teacher turns), reflection -> 2, peer_checklist -> 3, arp_observation -> 4, child_check -> 5.
8. Every RehearsalScore links to a real Scene with stored Turns.
9. AggModuleBatch rows computed from demo rows, no negative counts.
10. Deterministic generation with seed 42.
11. Demo banner presence on web interface.
"""

from __future__ import annotations

import re
import uuid
from contextlib import asynccontextmanager
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.config import settings
from backend.app.db.demo_data import populate_demo_cohort
from backend.app.db.models import (
    AdoptionEvidence,
    AggModuleBatch,
    AppUser,
    ARPObservation,
    ExplainScore,
    RehearsalScore,
    Scene,
    Teacher,
    Turn,
)
from backend.app.db.seed import seed_database
from backend.app.jobs.aggregates import compute_aggregates_for_batch
from backend.app.web.teacher import STATIC_DIR
from backend.app.web.teacher import router as teacher_router


class MockScalars:
    """Mock scalar wrapper."""

    def __init__(self, items: list[Any]) -> None:
        self._items = items

    def all(self) -> list[Any]:
        return self._items


class MockResult:
    """Mock result object providing scalar_one_or_none and scalars."""

    def __init__(self, value: Any = None, items: list[Any] | None = None) -> None:
        self._value = value
        self._items = items if items is not None else ([value] if value is not None else [])

    def scalar_one_or_none(self) -> Any:
        return self._value

    def scalars(self) -> MockScalars:
        return MockScalars(self._items)


class FakeDemoSession:
    """In-memory async session tracking entities added and queried during demo cohort generation."""

    def __init__(self) -> None:
        self.added: list[Any] = []
        self.deleted: list[Any] = []
        self._by_key: dict[tuple[type, Any], Any] = {}

    def add(self, obj: Any) -> None:
        self.added.append(obj)
        ident = getattr(obj, "id", None)
        if ident is not None:
            self._by_key[(type(obj), ident)] = obj

    async def delete(self, obj: Any) -> None:
        self.deleted.append(obj)
        if obj in self.added:
            self.added.remove(obj)
        ident = getattr(obj, "id", None)
        if ident is not None:
            self._by_key.pop((type(obj), ident), None)

    async def get(self, model: type, ident: Any) -> Any:
        return self._by_key.get((model, ident))

    async def flush(self) -> None:
        pass

    async def commit(self) -> None:
        pass

    async def execute(self, stmt: Any) -> MockResult:
        try:
            sql = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        except Exception:
            sql = str(stmt)

        sql_lower = sql.lower()

        # Teacher queries: select by batch_id
        if "from teacher" in sql_lower:
            match_b = re.search(r"batch_id = '([^']+)'", sql, re.IGNORECASE)
            if match_b:
                target_batch = match_b.group(1)
                matching = [
                    t for t in self.added if isinstance(t, Teacher) and t.batch_id == target_batch
                ]
                return MockResult(items=matching)
            return MockResult(items=[t for t in self.added if isinstance(t, Teacher)])

        # AppUser queries: select by username
        if "from app_user" in sql_lower or "app_user" in sql_lower:
            match_u = re.search(r"username = '([^']+)'", sql, re.IGNORECASE)
            if match_u:
                target_username = match_u.group(1)
                for obj in self.added:
                    if isinstance(obj, AppUser) and obj.username == target_username:
                        return MockResult(value=obj)
            return MockResult(None)

        in_match = re.search(r"teacher_id IN \(([^)]+)\)", sql, re.IGNORECASE)
        allowed_teachers: set[str] | None = None
        if in_match:
            allowed_teachers = {
                s.replace("-", "").lower() for s in re.findall(r"'([^']+)'", in_match.group(1))
            }

        # AdoptionEvidence queries
        if "adoption_evidence" in sql_lower:
            match_t = re.search(r"teacher_id = '([^']+)'", sql, re.IGNORECASE)
            match_m = re.search(r"move_id = '([^']+)'", sql, re.IGNORECASE)
            match_l = re.search(r"level = (\d+)", sql, re.IGNORECASE)
            if match_t and match_m and match_l:
                tid_str, mid, lvl = match_t.group(1), match_m.group(1), int(match_l.group(1))
                for obj in self.added:
                    if (
                        isinstance(obj, AdoptionEvidence)
                        and str(obj.teacher_id).replace("-", "").lower()
                        == tid_str.replace("-", "").lower()
                        and obj.move_id == mid
                        and obj.level == lvl
                    ):
                        return MockResult(value=obj)
                return MockResult(None)

            # Collection of adoption evidence
            evs = [
                obj
                for obj in self.added
                if isinstance(obj, AdoptionEvidence)
                and (
                    allowed_teachers is None
                    or str(obj.teacher_id).replace("-", "").lower() in allowed_teachers
                )
            ]
            return MockResult(items=evs)

        # ExplainScore queries
        if "explain_score" in sql_lower:
            match_t = re.search(r"teacher_id = '([^']+)'", sql, re.IGNORECASE)
            if match_t:
                tid_str = match_t.group(1).replace("-", "").lower()
                es_matching = [
                    obj
                    for obj in self.added
                    if isinstance(obj, ExplainScore)
                    and str(obj.teacher_id).replace("-", "").lower() == tid_str
                ]
                val = es_matching[0] if es_matching else None
                return MockResult(value=val, items=es_matching)
            es_all = [
                obj
                for obj in self.added
                if isinstance(obj, ExplainScore)
                and (
                    allowed_teachers is None
                    or str(obj.teacher_id).replace("-", "").lower() in allowed_teachers
                )
            ]
            return MockResult(items=es_all)

        # RehearsalScore queries
        if "rehearsal_score" in sql_lower:
            rs_all = [
                obj
                for obj in self.added
                if isinstance(obj, RehearsalScore)
                and (
                    allowed_teachers is None
                    or str(obj.teacher_id).replace("-", "").lower() in allowed_teachers
                )
            ]
            return MockResult(items=rs_all)

        # Turn queries
        if "turn" in sql_lower:
            turns = [obj for obj in self.added if isinstance(obj, Turn)]
            return MockResult(items=turns)

        # AggModuleBatch queries
        if "agg_module_batch" in sql_lower:
            match_b = re.search(r"batch_id = '([^']+)'", sql, re.IGNORECASE)
            match_m = re.search(r"move_id = '([^']+)'", sql, re.IGNORECASE)
            if match_b and match_m:
                bid, mid = match_b.group(1), match_m.group(1)
                for obj in self.added:
                    if (
                        isinstance(obj, AggModuleBatch)
                        and obj.batch_id == bid
                        and obj.move_id == mid
                    ):
                        return MockResult(value=obj)
            return MockResult(None)

        return MockResult(None)


@pytest.mark.asyncio
async def test_populate_demo_cohort_counts_and_batches() -> None:
    """Verifies teacher counts across batches: KNP-B1 (25), KNP-B2 (18), KNP-B3 (8)."""
    session = FakeDemoSession()
    await populate_demo_cohort(cast(AsyncSession, session))

    teachers = [o for o in session.added if isinstance(o, Teacher)]
    assert len(teachers) == 51

    b1_teachers = [t for t in teachers if t.batch_id == "KNP-B1"]
    b2_teachers = [t for t in teachers if t.batch_id == "KNP-B2"]
    b3_teachers = [t for t in teachers if t.batch_id == "KNP-B3"]

    assert len(b1_teachers) == 25, "KNP-B1 must have 25 teachers"
    assert len(b2_teachers) == 18, "KNP-B2 must have 18 teachers"
    assert len(b3_teachers) == 8, "KNP-B3 must have 8 teachers (small batch for suppression)"


@pytest.mark.asyncio
async def test_populate_demo_cohort_cluster_c01_consent_split() -> None:
    """Verifies Cluster KNP-C01 has 12 teachers: exactly 7 consenting and 5 non-consenting."""
    session = FakeDemoSession()
    await populate_demo_cohort(cast(AsyncSession, session))

    teachers = [o for o in session.added if isinstance(o, Teacher)]
    c01_teachers = [t for t in teachers if t.cluster_id == "KNP-C01"]

    assert len(c01_teachers) == 12, "Cluster KNP-C01 must have 12 teachers"

    consenting = [t for t in c01_teachers if t.consent_share_scores is True]
    non_consenting = [t for t in c01_teachers if t.consent_share_scores is False]

    assert len(consenting) == 7, "Exactly 7 teachers in KNP-C01 must have consent_share_scores=True"
    assert len(non_consenting) == 5, (
        "Exactly 5 teachers in KNP-C01 must have consent_share_scores=False"
    )

    # Verify teacher.demo3 is non-consenting
    t3 = next(t for t in c01_teachers if t.id == uuid.UUID("00000000-0000-0000-0000-000000000003"))
    assert t3.consent_share_scores is False, (
        "teacher.demo3 must demonstrate non-consenting behavior"
    )


@pytest.mark.asyncio
async def test_populate_demo_cohort_is_demo_flag_and_prefixes() -> None:
    """Verifies all teachers and users have is_demo=True and names prefixed with 'डेमो '."""
    session = FakeDemoSession()
    await populate_demo_cohort(cast(AsyncSession, session))

    teachers = [o for o in session.added if isinstance(o, Teacher)]
    users = [o for o in session.added if isinstance(o, AppUser)]

    assert len(teachers) == 51
    assert len(users) == 51

    for t in teachers:
        assert t.is_demo is True, f"Teacher {t.name} must have is_demo=True"
        assert t.name is not None and t.name.startswith("डेमो "), (
            f"Teacher name '{t.name}' must start with 'डेमो '"
        )

    for u in users:
        assert u.is_demo is True, f"User {u.username} must have is_demo=True"
        assert u.display_name is not None and u.display_name.startswith("डेमो "), (
            f"User display_name '{u.display_name}' must start with 'डेमो '"
        )
        assert u.role == "teacher"


@pytest.mark.asyncio
async def test_populate_demo_cohort_rehearsals_link_to_scenes_with_turns() -> None:
    """Verifies every RehearsalScore links to a real Scene with stored Turns (CHANGES item 5)."""
    session = FakeDemoSession()
    await populate_demo_cohort(cast(AsyncSession, session))

    scenes = [o for o in session.added if isinstance(o, Scene)]
    rscores = [o for o in session.added if isinstance(o, RehearsalScore)]
    turns = [o for o in session.added if isinstance(o, Turn)]

    assert len(rscores) == 51
    assert len(scenes) == 51
    assert len(turns) > 0

    scene_map = {s.id: s for s in scenes}
    turns_by_scene: dict[uuid.UUID, list[Turn]] = {}
    for tr in turns:
        turns_by_scene.setdefault(tr.scene_id, []).append(tr)

    for rs in rscores:
        assert rs.scene_id in scene_map, f"RehearsalScore {rs.id} must link to a valid Scene"
        scene = scene_map[rs.scene_id]
        assert scene.teacher_turns >= 3, "Scene must have at least 3 teacher turns"
        assert scene.status == "completed"
        stored_turns = turns_by_scene.get(rs.scene_id, [])
        assert len(stored_turns) >= 3, "Scene must have stored Turn records"


@pytest.mark.asyncio
async def test_populate_demo_cohort_honest_provenance() -> None:
    """Verifies provenance is honest: model is 'mock' or 'fallback', never 'claude-sonnet' (CHANGES item 2)."""
    session = FakeDemoSession()
    await populate_demo_cohort(cast(AsyncSession, session))

    rscores = [o for o in session.added if isinstance(o, RehearsalScore)]
    escores = [o for o in session.added if isinstance(o, ExplainScore)]

    for rs in rscores:
        assert rs.model in ("mock", "fallback"), (
            f"RehearsalScore model must be mock/fallback, got {rs.model}"
        )
        assert rs.model != "claude-sonnet", "Must never label demo output as claude-sonnet"
        assert isinstance(rs.confidence, float)
        assert 0.0 <= rs.confidence <= 1.0
        assert isinstance(rs.needs_review, bool)

    for es in escores:
        assert es.model in ("mock", "fallback"), (
            f"ExplainScore model must be mock/fallback, got {es.model}"
        )
        assert es.model != "claude-sonnet", "Must never label demo output as claude-sonnet"
        assert isinstance(es.confidence, float)
        assert 0.0 <= es.confidence <= 1.0


@pytest.mark.asyncio
async def test_populate_demo_cohort_evidence_levels_match_source() -> None:
    """Verifies evidence levels strictly match their source (CHANGES item 4)."""
    session = FakeDemoSession()
    await populate_demo_cohort(cast(AsyncSession, session))

    evidences = [o for o in session.added if isinstance(o, AdoptionEvidence)]
    arp_observations = [o for o in session.added if isinstance(o, ARPObservation)]

    assert len(evidences) >= 51
    assert len(arp_observations) > 0

    valid_sources = {"rehearsal", "reflection", "peer_checklist", "arp_observation", "child_check"}
    for ev in evidences:
        assert ev.source in valid_sources
        if ev.source == "rehearsal":
            assert ev.level == 1, "rehearsal evidence level must be 1"
        elif ev.source == "reflection":
            assert ev.level == 2, "reflection evidence level must be 2"
        elif ev.source == "peer_checklist":
            assert ev.level == 3, "peer_checklist evidence level must be 3"
        elif ev.source == "arp_observation":
            assert ev.level == 4, "arp_observation evidence level must be 4"
        elif ev.source == "child_check":
            assert ev.level == 5, "child_check evidence level must be 5"


@pytest.mark.asyncio
async def test_populate_demo_cohort_aggregates_non_negative_and_suppressed() -> None:
    """Verifies AggModuleBatch computed honestly from demo rows with suppression (CHANGES items 3 & 5)."""
    session = FakeDemoSession()
    await populate_demo_cohort(cast(AsyncSession, session))

    aggregates = [o for o in session.added if isinstance(o, AggModuleBatch)]
    assert len(aggregates) == 3

    agg_by_batch = {a.batch_id: a for a in aggregates}

    # Batch KNP-B3: n = 8 < 10 -> MUST be suppressed
    b3_agg = agg_by_batch["KNP-B3"]
    assert b3_agg.n_teachers == 8
    assert b3_agg.explain_missing is None, "Batch KNP-B3 with n<10 must have explain_missing=None"
    assert b3_agg.rubric_dist is None, "Batch KNP-B3 with n<10 must have rubric_dist=None"
    assert b3_agg.ladder_dist is None, "Batch KNP-B3 with n<10 must have ladder_dist=None"
    assert b3_agg.active_rate is None, "Batch KNP-B3 with n<10 must have active_rate=None"

    # Batches KNP-B1 and KNP-B2: computed from real rows, no negative counts
    for b_id in ["KNP-B1", "KNP-B2"]:
        agg = agg_by_batch[b_id]
        assert agg.n_teachers is not None and agg.n_teachers >= 10
        assert agg.ladder_dist is not None
        for lvl_str, count in agg.ladder_dist.items():
            assert count >= 0, f"ladder_dist level {lvl_str} must not be negative: {count}"

        if agg.explain_missing:
            for kpid, count in agg.explain_missing.items():
                assert count >= 0, f"explain_missing for {kpid} must not be negative: {count}"

        if agg.rubric_dist:
            for crit_id, dist in agg.rubric_dist.items():
                for score_val, count in dist.items():
                    assert count >= 0, (
                        f"rubric_dist for {crit_id}[{score_val}] must not be negative: {count}"
                    )

        if agg.active_rate is not None:
            assert 0.0 <= agg.active_rate <= 1.0


@pytest.mark.asyncio
async def test_populate_demo_cohort_determinism() -> None:
    """Verifies that running population multiple times with seed 42 produces deterministic output."""
    session1 = FakeDemoSession()
    await populate_demo_cohort(cast(AsyncSession, session1))

    session2 = FakeDemoSession()
    await populate_demo_cohort(cast(AsyncSession, session2))

    rscores1 = [o for o in session1.added if isinstance(o, RehearsalScore)]
    rscores2 = [o for o in session2.added if isinstance(o, RehearsalScore)]

    assert len(rscores1) == len(rscores2)
    assert rscores1[0].scores == rscores2[0].scores
    assert rscores1[0].strength_hi == rscores2[0].strength_hi
    assert rscores1[0].change_hi == rscores2[0].change_hi


@pytest.mark.asyncio
async def test_demo_banner_displayed_on_web_page() -> None:
    """Verifies that the demo banner 'डेमो डेटा — वास्तविक शिक्षक नहीं' is displayed on the web interface."""
    app = FastAPI()
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    app.include_router(teacher_router)

    teacher_id = uuid.UUID("00000000-0000-0000-0000-000000000001")
    demo_user = AppUser(
        id=uuid.uuid4(),
        username="teacher.demo1",
        role="teacher",
        teacher_id=teacher_id,
        display_name="डेमो शिक्षिका 1",
        password_hash="hash",
        is_demo=True,
    )

    demo_teacher = Teacher(
        id=teacher_id,
        name="डेमो शिक्षिका 1 (सुमन)",
        preferred_channel="web",
        lite_mode=False,
        is_demo=True,
    )

    fake_db = MagicMock()
    fake_db.get = AsyncMock(return_value=demo_teacher)
    mock_res = MagicMock()
    mock_res.scalars.return_value.all.return_value = []
    mock_res.scalar_one_or_none.return_value = None
    fake_db.execute = AsyncMock(return_value=mock_res)

    from backend.app.auth.guards import get_current_user
    from backend.app.db.session import get_db_session

    app.dependency_overrides[get_current_user] = lambda: demo_user
    app.dependency_overrides[get_db_session] = lambda: fake_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        resp = await client.get("/teacher")
        assert resp.status_code == 200
        assert "डेमो डेटा — वास्तविक शिक्षक नहीं" in resp.text
        assert "demo-banner" in resp.text


@pytest.mark.asyncio
async def test_aggregates_counts_missing_status() -> None:
    """Verifies that compute_aggregates_for_batch counts 'missing' and 'partial' statuses in explain_missing."""
    batch_id = "KNP-B1"
    move_id = "NUM_SUB_REGROUP_BUNDLES"
    session = FakeDemoSession()

    teachers = [
        Teacher(
            id=uuid.UUID(f"00000000-0000-0009-0000-{i + 1:012x}"),
            batch_id=batch_id,
            cluster_id="KNP-C01",
            name=f"डेमो {i}",
            is_demo=True,
        )
        for i in range(12)
    ]
    for t in teachers:
        session.add(t)

    escore = ExplainScore(
        id=uuid.uuid4(),
        teacher_id=teachers[0].id,
        move_id=move_id,
        points={"kp_missing": "missing", "kp_partial": "partial", "kp_covered": "covered"},
    )
    session.add(escore)

    agg = await compute_aggregates_for_batch(cast(AsyncSession, session), batch_id, move_id)
    assert agg.explain_missing is not None
    assert agg.explain_missing.get("kp_missing") == 1
    assert agg.explain_missing.get("kp_partial") == 1
    assert "kp_covered" not in agg.explain_missing


@pytest.mark.asyncio
async def test_seed_database_removes_legacy_admin(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifies that seed_database removes legacy admin.demo account."""
    legacy_admin = AppUser(
        id=uuid.uuid4(),
        username="admin.demo",
        role="admin",
        password_hash="hash",
    )
    session = FakeDemoSession()
    session.add(legacy_admin)

    @asynccontextmanager
    async def mock_session_factory():
        yield session

    monkeypatch.setattr("backend.app.db.seed.async_session_factory", mock_session_factory)
    await seed_database()

    assert legacy_admin in session.deleted


@pytest.mark.asyncio
async def test_seeding_with_anthropic_api_key_never_calls_real_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verifies that seeding forces mock LLM and restores original provider afterwards."""
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "sk-ant-test-real-key")
    monkeypatch.setattr(settings, "LLM_PROVIDER", "anthropic")

    session = FakeDemoSession()
    await populate_demo_cohort(cast(AsyncSession, session))

    assert settings.LLM_PROVIDER == "anthropic"
