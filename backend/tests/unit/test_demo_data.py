"""Unit tests for synthetic demo cohort data (spec/03 §3.5, T31).

Verifies:
1. Teacher cohort counts across batches (KNP-B1: 25, KNP-B2: 18, KNP-B3: 8).
2. Suppression demonstration for batch KNP-B3 (n < 10).
3. Cluster KNP-C01 teacher count (12) and exact consent split (7 True, 5 False).
4. All teachers and users have is_demo=True and names prefixed with 'डेमो '.
5. Real rehearsal scores and explain scores generated via pedagogical rules/engine.
6. Deterministic generation.
7. Demo banner presence on web interface when demo_mode is True.
"""

from __future__ import annotations

import re
import uuid
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.demo_data import populate_demo_cohort
from backend.app.db.models import (
    AdoptionEvidence,
    AggModuleBatch,
    AppUser,
    ExplainScore,
    RehearsalScore,
    Scene,
    Teacher,
)
from backend.app.web.teacher import STATIC_DIR
from backend.app.web.teacher import router as teacher_router


class MockResult:
    """Mock result object providing scalar_one_or_none."""

    def __init__(self, value: Any = None) -> None:
        self._value = value

    def scalar_one_or_none(self) -> Any:
        return self._value


class FakeDemoSession:
    """In-memory async session tracking entities added and queried during demo cohort generation."""

    def __init__(self) -> None:
        self.added: list[Any] = []
        self._by_key: dict[tuple[type, Any], Any] = {}

    def add(self, obj: Any) -> None:
        self.added.append(obj)
        ident = getattr(obj, "id", None)
        if ident is not None:
            self._by_key[(type(obj), ident)] = obj

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

        if "app_user" in sql.lower():
            # Check for username match
            match = re.search(r"username = '([^']+)'", sql, re.IGNORECASE)
            if match:
                target_username = match.group(1)
                for obj in self.added:
                    if isinstance(obj, AppUser) and obj.username == target_username:
                        return MockResult(obj)
            return MockResult(None)

        if "adoption_evidence" in sql.lower():
            match_t = re.search(r"teacher_id = '([^']+)'", sql, re.IGNORECASE)
            match_m = re.search(r"move_id = '([^']+)'", sql, re.IGNORECASE)
            if match_t and match_m:
                tid_str, mid = match_t.group(1), match_m.group(1)
                for obj in self.added:
                    if (
                        isinstance(obj, AdoptionEvidence)
                        and str(obj.teacher_id) == tid_str
                        and obj.move_id == mid
                    ):
                        return MockResult(obj)
            return MockResult(None)

        if "agg_module_batch" in sql.lower():
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
                        return MockResult(obj)
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
    assert len(non_consenting) == 5, "Exactly 5 teachers in KNP-C01 must have consent_share_scores=False"

    # Verify teacher.demo3 (index 3) is among the non-consenting teachers
    t3 = next(t for t in c01_teachers if t.id == uuid.UUID("00000000-0000-0000-0000-000000000003"))
    assert t3.consent_share_scores is False, "teacher.demo3 must demonstrate non-consenting behavior"


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
        assert t.name is not None and t.name.startswith("डेमो "), f"Teacher name '{t.name}' must start with 'डेमो '"

    for u in users:
        assert u.is_demo is True, f"User {u.username} must have is_demo=True"
        assert u.display_name is not None and u.display_name.startswith("डेमो "), f"User display_name '{u.display_name}' must start with 'डेमो '"
        assert u.role == "teacher"


@pytest.mark.asyncio
async def test_populate_demo_cohort_real_engine_scores() -> None:
    """Verifies rehearsal scores and explain scores are generated using pedagogical engine and rubrics."""
    session = FakeDemoSession()
    await populate_demo_cohort(cast(AsyncSession, session))

    scenes = [o for o in session.added if isinstance(o, Scene)]
    rscores = [o for o in session.added if isinstance(o, RehearsalScore)]
    escores = [o for o in session.added if isinstance(o, ExplainScore)]
    evidences = [o for o in session.added if isinstance(o, AdoptionEvidence)]
    aggregates = [o for o in session.added if isinstance(o, AggModuleBatch)]

    assert len(scenes) == 51
    assert len(rscores) == 51
    assert len(escores) == 51
    assert len(evidences) == 51
    assert len(aggregates) == 3

    # Check that RehearsalScore contains real rubric scores and non-invented pedagogical feedback
    sample_rscore = rscores[0]
    assert isinstance(sample_rscore.scores, dict)
    assert len(sample_rscore.scores) > 0
    for crit_id, val in sample_rscore.scores.items():
        assert isinstance(crit_id, str)
        assert isinstance(val, int)
        assert 0 <= val <= 2

    assert sample_rscore.strength_hi != ""
    assert sample_rscore.change_hi != ""
    assert sample_rscore.exact_words_hi != ""

    # Check ExplainScore contains real points analysis
    sample_escore = escores[0]
    assert isinstance(sample_escore.points, dict)
    assert len(sample_escore.points) > 0
    assert sample_escore.transcript != ""

    # Check AggModuleBatch has counts
    batch_map = {agg.batch_id: agg.n_teachers for agg in aggregates}
    assert batch_map["KNP-B1"] == 25
    assert batch_map["KNP-B2"] == 18
    assert batch_map["KNP-B3"] == 8


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
        # Request with demo=1 or user.is_demo=True
        resp = await client.get("/teacher")
        assert resp.status_code == 200
        assert "डेमो डेटा — वास्तविक शिक्षक नहीं" in resp.text
        assert "demo-banner" in resp.text
