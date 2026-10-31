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

import ast
import re
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.config import settings
from backend.app.db.demo_data import (
    DEMO_GAP_SCENE_PREFIX,
    SEED_TEACHER_IDS,
    populate_demo_cohort,
    repair_onboarding_state,
)
from backend.app.db.models import (
    AdoptionEvidence,
    AggModuleBatch,
    AppUser,
    ARPObservation,
    ExplainScore,
    MovePath,
    RehearsalScore,
    Scene,
    SessionState,
    Teacher,
    Turn,
)
from backend.app.db.seed import seed_database
from backend.app.jobs.aggregates import compute_aggregates_for_batch
from backend.app.sessions.state_machine import OnboardingStateEnum
from backend.app.web.teacher import STATIC_DIR
from backend.app.web.teacher import router as teacher_router


class MockScalars:
    """Mock scalar wrapper."""

    def __init__(self, items: list[Any]) -> None:
        self._items = items

    def all(self) -> list[Any]:
        return self._items

    def first(self) -> Any:
        return self._items[0] if self._items else None


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

    # the trainer's "Where training is not landing" demo scenes (T3) carry no score: leave them out
    gap = DEMO_GAP_SCENE_PREFIX
    scenes = [o for o in session.added if isinstance(o, Scene) and not str(o.id).startswith(gap)]
    rscores = [o for o in session.added if isinstance(o, RehearsalScore)]
    scene_ids = {s.id for s in scenes}
    turns = [o for o in session.added if isinstance(o, Turn) and o.scene_id in scene_ids]

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
        assert scene.status == "ended"  # check_scene_status allows only 'active' / 'ended'
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
        start_seen_at=datetime.now(UTC),
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
        assert "डेमो: नई शुरुआत। पूरा परिचय और पहला अभ्यास करें।" in resp.text
        banner = resp.text.split('id="demo-banner"')[1].split("</div>")[0]
        assert 'href="/logout"' not in banner, "one Log out only: the top bar has it (fix5)"
        assert 'id="demo-dismiss"' in banner, "and the banner can be dismissed"


def test_demo_banner_text_says_what_each_demo_shows_in_both_languages() -> None:
    """fix3 K5: one banner per demo account, in both languages, no dashes."""
    from backend.app.core.messages import get_message, set_ui_lang
    from backend.app.web.teacher import _demo_banner_text

    def teacher(login: str) -> AppUser:
        return AppUser(username=login, role="teacher", password_hash="x", is_demo=True)

    other = AppUser(username="arp.demo", role="arp", password_hash="x", is_demo=True)
    expected = {
        "hi": {
            "teacher.demo1": "डेमो: नई शुरुआत। पूरा परिचय और पहला अभ्यास करें।",
            "teacher.demo2": "डेमो: दूसरे हफ़्ते की शिक्षिका। रवि से 43 − 27 पर बात करें, फिर 'अब भी अटके हैं' दबाएँ, और 'मेरी प्रगति' खोलें।",
            "teacher.demo3": "डेमो: कक्षा के बारे में बताने के बाद ऐप ने पढ़ने का तरीका चुना (मात्रा)। 'समझ गई, आगे' दबाकर अभ्यास करें।",
        },
        "en": {
            "teacher.demo1": "Demo: a fresh start. Do the intro and first practice.",
            "teacher.demo2": "Demo: a teacher in her second week. Talk to Ravi about 43 − 27, then press 'Still stuck', and open 'My progress'.",
            "teacher.demo3": "Demo: after describing the class, the app chose a reading move (matras). Press 'Got it, next' and practise.",
        },
    }
    for lang, per_login in expected.items():
        set_ui_lang(lang)
        try:
            for login, text in per_login.items():
                shown = _demo_banner_text(teacher(login), 1)  # the first step of the demo
                assert shown == text
                # past the step it describes, and on pages that do not know the step: the plain line
                plain = get_message("ui_demo_account_banner")
                assert _demo_banner_text(teacher(login), 7) == plain
                assert _demo_banner_text(teacher(login)) == plain
                assert "—" not in shown and "–" not in shown
                if lang == "hi" and shown == text:  # no English left in the Hindi banner
                    assert not any("a" <= c.lower() <= "z" for c in shown), shown
            assert _demo_banner_text(other) == get_message("ui_demo_banner")
        finally:
            set_ui_lang("hi")
    # the shown button names exist in the catalog (demo3: the learn step button)
    assert "'समझ गई, आगे'" in expected["hi"]["teacher.demo3"]
    assert get_message("btn_understood", "f", lang="hi") == "समझ गई, आगे"
    assert get_message("btn_understood", "f", lang="en") == "Got it, next"
    assert "demo-banner:empty" in (STATIC_DIR / "app.css").read_text(encoding="utf-8").replace(
        ".demo-banner:empty", "demo-banner:empty"
    )


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
    monkeypatch.setattr(
        "backend.app.llm.client.get_anthropic_client",
        MagicMock(
            side_effect=RuntimeError("Real Anthropic client must never be called during seeding")
        ),
    )
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "sk-ant-test-real-key")
    monkeypatch.setattr(settings, "LLM_PROVIDER", "anthropic")

    session = FakeDemoSession()
    await populate_demo_cohort(cast(AsyncSession, session))

    assert settings.LLM_PROVIDER == "anthropic"


# ── Onboarding state validity (live bug: "COMPLETE" is not an OnboardingStateEnum) ──

_ONBOARDING_SOURCES = (
    Path(__file__).parents[2] / "app" / "db" / "seed.py",
    Path(__file__).parents[2] / "app" / "db" / "demo_data.py",
    Path(__file__).parents[2] / "app" / "web" / "admin.py",
)


def _onboarding_value_nodes(tree: ast.AST) -> list[ast.expr]:
    """Returns every expression assigned to onboarding_state (kwarg or attribute)."""
    nodes: list[ast.expr] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.keyword) and node.arg == "onboarding_state":
            nodes.append(node.value)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Attribute) and target.attr == "onboarding_state":
                    nodes.append(node.value)
    return nodes


def test_seed_and_admin_onboarding_values_are_valid_enum_members() -> None:
    valid = {state.value for state in OnboardingStateEnum}
    checked = 0
    for path in _ONBOARDING_SOURCES:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for value in _onboarding_value_nodes(tree):
            where = f"{path.name}:{value.lineno}"
            if isinstance(value, ast.Constant):
                assert value.value in valid, f"{where}: invalid onboarding_state {value.value!r}"
            elif isinstance(value, ast.Attribute):
                assert isinstance(value.value, ast.Name)
                assert value.value.id == "OnboardingStateEnum", where
                assert value.attr in OnboardingStateEnum.__members__, where
            else:
                # Computed values (e.g. onboarding_target) are covered by the behavioural tests below
                assert isinstance(value, ast.Name), (
                    f"{where}: unexpected onboarding_state expression"
                )
            checked += 1
    assert checked >= 6


def test_repair_onboarding_state_fixes_invalid_and_keeps_valid() -> None:
    legacy = Teacher(id=uuid.uuid4(), onboarding_state="COMPLETE")
    repair_onboarding_state(legacy, OnboardingStateEnum.READY)
    assert legacy.onboarding_state == "READY"

    progressed = Teacher(id=uuid.uuid4(), onboarding_state="PLACEMENT")
    repair_onboarding_state(progressed, OnboardingStateEnum.READY)
    assert progressed.onboarding_state == "PLACEMENT"


async def _run_seed_with(session: FakeDemoSession, monkeypatch: pytest.MonkeyPatch) -> None:
    @asynccontextmanager
    async def mock_session_factory():  # type: ignore[no-untyped-def]
        yield session

    monkeypatch.setattr("backend.app.db.seed.async_session_factory", mock_session_factory)
    await seed_database()


@pytest.mark.asyncio
async def test_seed_writes_only_valid_onboarding_states(monkeypatch: pytest.MonkeyPatch) -> None:
    session = FakeDemoSession()
    await _run_seed_with(session, monkeypatch)

    teachers = {t.id: t for t in session.added if isinstance(t, Teacher)}
    assert len(teachers) == 51
    for teacher in teachers.values():
        OnboardingStateEnum(teacher.onboarding_state)  # raises ValueError if invalid
    assert teachers[SEED_TEACHER_IDS[0]].onboarding_state == "NEW"
    assert teachers[SEED_TEACHER_IDS[1]].onboarding_state == "READY"
    assert teachers[SEED_TEACHER_IDS[2]].onboarding_state == "READY"


@pytest.mark.asyncio
async def test_reseed_repairs_legacy_complete_onboarding_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Rows written by the old seed ("COMPLETE") are repaired by one re-run."""
    session = FakeDemoSession()
    legacy_ids = [
        SEED_TEACHER_IDS[1],
        SEED_TEACHER_IDS[2],
        uuid.UUID(f"00000000-0000-0000-0002-{7:012x}"),
    ]
    for teacher_id in legacy_ids:
        session.add(Teacher(id=teacher_id, is_demo=True, onboarding_state="COMPLETE"))
    # demo1 is a shared login: the seed now resets it to NEW. Other cohort teachers keep progress.
    progressed = Teacher(
        id=uuid.UUID(f"00000000-0000-0000-0002-{8:012x}"),
        is_demo=True,
        onboarding_state="PLACEMENT",
    )
    session.add(progressed)

    await _run_seed_with(session, monkeypatch)

    for teacher_id in legacy_ids:
        teacher = await session.get(Teacher, teacher_id)
        assert teacher is not None
        assert teacher.onboarding_state == "READY"
    assert progressed.onboarding_state == "PLACEMENT"  # valid progress is left alone


MOVES_DIR = Path(__file__).parents[3] / "content" / "moves"


@pytest.mark.asyncio
async def test_seed_writes_only_move_ids_with_move_cards(monkeypatch: pytest.MonkeyPatch) -> None:
    """Live bug: seeded rows referenced m_sub_regroup_intro, which has no move card."""
    session = FakeDemoSession()
    await _run_seed_with(session, monkeypatch)

    move_ids = {
        obj.move_id
        for obj in session.added
        if isinstance(obj, (SessionState, MovePath, AdoptionEvidence, Scene, RehearsalScore))
        and obj.move_id
    }
    move_ids |= {
        str(obj.context["current_move_id"])
        for obj in session.added
        if isinstance(obj, SessionState) and obj.context and obj.context.get("current_move_id")
    }
    assert move_ids, "seed wrote no move ids"
    missing = sorted(m for m in move_ids if not (MOVES_DIR / f"{m}.yaml").is_file())
    assert missing == [], f"seeded move ids without a move card: {missing}"
