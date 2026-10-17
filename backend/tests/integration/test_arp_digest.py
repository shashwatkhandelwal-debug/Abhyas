"""Integration tests for DB-backed ARP digest, access scoping, and privacy (spec/09 §9.3, T32).

Verifies against PostgreSQL:
1. Non-consenting teacher never appears by name or score anywhere in the digest.
2. Aggregate row "अन्य N शिक्षक (स्कोर साझा नहीं)" accurately counts non-consenting teachers.
3. Teachers from other clusters are completely excluded from the digest.
4. Suggested visit list strictly includes consenting teachers only.
5. Classroom observation POST creates ARPObservation and AdoptionEvidence level 4.
6. Question answer POST updates Question.answer_hi, resolves ReviewItem, and queues outbound Message.
7. Escalated questions from non-consenting teachers are displayed with anonymised code 'शिक्षक #<short hash>'.
"""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from backend.app.auth.csrf import generate_csrf_token
from backend.app.auth.guards import get_current_user
from backend.app.db.models import (
    AdoptionEvidence,
    AppUser,
    ARPObservation,
    Cluster,
    Message,
    Question,
    RehearsalScore,
    ReviewItem,
    Teacher,
)
from backend.app.db.session import get_db_session
from backend.app.main import app
from backend.app.reports.arp_digest import build_arp_digest

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL not set (runs in CI with real pgvector/pgvector:pg16)",
)


def get_async_db_url() -> str:
    url = TEST_DATABASE_URL or ""
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if "postgresql+psycopg2://" in url:
        return url.replace("postgresql+psycopg2://", "postgresql+asyncpg://")
    return url


@pytest.fixture
async def session_factory() -> AsyncGenerator[async_sessionmaker[AsyncSession], None]:
    async_url = get_async_db_url()
    engine = create_async_engine(async_url, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with factory() as session:
        await session.merge(Cluster(id="KNP-C01", name="कल्याणपुर क्लस्टर 1"))
        await session.merge(Cluster(id="KNP-C02", name="कल्याणपुर क्लस्टर 2"))
        await session.commit()
    yield factory
    await engine.dispose()


@pytest.mark.asyncio
async def test_non_consenting_teacher_never_appears_by_name_or_score(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Non-consenting teachers must NEVER appear in consenting list, visit list, or HTML table."""
    async with session_factory() as session:
        arp_user = AppUser(
            id=uuid4(),
            username=f"arp.test.{uuid4().hex[:6]}",
            password_hash="hash",
            role="arp",
            cluster_id="KNP-C01",
        )
        session.add(arp_user)

        # Consenting teacher in cluster 1
        t_consent = Teacher(
            id=uuid4(),
            name="सुनीता_कंसेंट",
            school_id="प्रा.वि. कल्यानपुर",
            cluster_id="KNP-C01",
            consent_share_scores=True,
            is_demo=False,
        )
        session.add(t_consent)

        # Non-consenting teacher in cluster 1
        t_non_consent = Teacher(
            id=uuid4(),
            name="रीता_सीक्रेट",
            school_id="प्रा.वि. कल्यानपुर 2",
            cluster_id="KNP-C01",
            consent_share_scores=False,
            is_demo=False,
        )
        session.add(t_non_consent)

        # Rehearsal scores
        session.add(
            RehearsalScore(
                teacher_id=t_consent.id,
                move_id="NUM_SUB_REGROUP_BUNDLES",
                scores={"crit_1": 2, "crit_2": 2},
                evidence={},
            )
        )
        session.add(
            RehearsalScore(
                teacher_id=t_non_consent.id,
                move_id="NUM_SUB_REGROUP_BUNDLES",
                scores={"crit_1": 0, "crit_2": 0},
                evidence={},
            )
        )
        await session.commit()

        # Build digest
        digest = await build_arp_digest(session, arp_user)

        # Assertions on data structures
        assert digest.total_teachers >= 2
        assert digest.non_consenting_count >= 1

        consenting_names = [t.name for t in digest.consenting_teachers]
        assert "सुनीता_कंसेंट" in consenting_names
        assert "रीता_सीक्रेट" not in consenting_names

        visit_names = [v.name for v in digest.suggested_visits]
        assert "रीता_सीक्रेट" not in visit_names

    # Assertions on rendered HTTP HTML page
    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as s:
            yield s

    async def override_get_current_user() -> AppUser:
        return arp_user

    app.dependency_overrides[get_db_session] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            res = await client.get("/arp")
            assert res.status_code == 200
            html = res.text

            # Consenting teacher must be visible
            assert "सुनीता_कंसेंट" in html
            # Non-consenting teacher name must NEVER appear
            assert "रीता_सीक्रेट" not in html
            # Aggregate row must be visible
            assert "स्कोर साझा नहीं" in html
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_other_cluster_teacher_never_appears(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Teachers belonging to a different cluster must be completely excluded."""
    async with session_factory() as session:
        arp_user = AppUser(
            id=uuid4(),
            username=f"arp.test.{uuid4().hex[:6]}",
            password_hash="hash",
            role="arp",
            cluster_id="KNP-C01",
        )
        session.add(arp_user)

        # Teacher in Cluster 2 (different cluster)
        t_cluster2 = Teacher(
            id=uuid4(),
            name="मीरा_अन्य_क्लस्टर",
            school_id="प्रा.वि. अन्य",
            cluster_id="KNP-C02",
            consent_share_scores=True,
            is_demo=False,
        )
        session.add(t_cluster2)
        await session.commit()

        digest = await build_arp_digest(session, arp_user)

        for t in digest.consenting_teachers:
            assert t.name != "मीरा_अन्य_क्लस्टर"
        for v in digest.suggested_visits:
            assert v.name != "मीरा_अन्य_क्लस्टर"


@pytest.mark.asyncio
async def test_arp_observation_creates_level_4_evidence(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Submitting observation form creates ARPObservation and AdoptionEvidence level 4."""
    async with session_factory() as session:
        arp_user = AppUser(
            id=uuid4(),
            username=f"arp.test.{uuid4().hex[:6]}",
            password_hash="hash",
            role="arp",
            cluster_id="KNP-C01",
        )
        session.add(arp_user)

        t = Teacher(
            id=uuid4(),
            name="पूजा",
            cluster_id="KNP-C01",
            consent_share_scores=True,
            is_demo=False,
        )
        session.add(t)
        await session.commit()
        teacher_id = t.id
        user_id = arp_user.id

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as s:
            yield s

    async def override_get_current_user() -> AppUser:
        return arp_user

    app.dependency_overrides[get_db_session] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user

    try:
        csrf_token = generate_csrf_token()
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport,
            base_url="http://testserver",
            cookies={"abhyas_csrf": csrf_token},
        ) as client:
            form_payload = {
                "csrf_token": csrf_token,
                "teacher_id": str(teacher_id),
                "move_id": "NUM_SUB_REGROUP_BUNDLES",
                "observed_on": "2026-10-17",
                "notes": "कक्षा में तीलियों के बंडल का अच्छा उपयोग देखा।",
                "check_1": "true",
                "check_2": "true",
            }
            res = await client.post("/arp/observation", data=form_payload, follow_redirects=False)
            assert res.status_code == 303
            assert "/arp?saved=1&msg=obs" in res.headers["location"]

        # Verify DB rows
        async with session_factory() as session:
            # 1. ARPObservation
            obs_res = await session.scalars(
                select(ARPObservation).where(ARPObservation.teacher_id == teacher_id)
            )
            obs = obs_res.first()
            assert obs is not None
            assert obs.arp_user_id == user_id
            assert obs.move_id == "NUM_SUB_REGROUP_BUNDLES"
            assert obs.checklist == {"1": True, "2": True}
            assert "तीलियों के बंडल" in (obs.notes or "")

            # 2. AdoptionEvidence Level 4
            ev_res = await session.scalars(
                select(AdoptionEvidence).where(
                    AdoptionEvidence.teacher_id == teacher_id,
                    AdoptionEvidence.source == "arp_observation",
                )
            )
            ev = ev_res.first()
            assert ev is not None
            assert ev.level == 4
            assert ev.created_by == user_id
            assert ev.detail is not None
            assert str(obs.id) == ev.detail.get("observation_id")
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_arp_answer_resolves_review_item_and_dispatches_message(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Answering escalated question marks Question answered, resolves ReviewItem, and queues outbound Message."""
    async with session_factory() as session:
        arp_user = AppUser(
            id=uuid4(),
            username=f"arp.test.{uuid4().hex[:6]}",
            password_hash="hash",
            role="arp",
            cluster_id="KNP-C01",
        )
        session.add(arp_user)

        t = Teacher(
            id=uuid4(),
            name="कविता",
            cluster_id="KNP-C01",
            consent_share_scores=True,
            preferred_channel="web",
            is_demo=False,
        )
        session.add(t)

        q = Question(
            id=uuid4(),
            teacher_id=t.id,
            text="रवि को इकाई और दहाई में भ्रम है, क्या करूँ?",
            category="pedagogy",
            status="escalated",
        )
        session.add(q)

        item = ReviewItem(
            id=uuid4(),
            kind="question",
            ref_id=str(q.id),
            reason="Teacher requested ARP escalation",
            status="open",
        )
        session.add(item)
        await session.commit()
        q_id = q.id
        t_id = t.id
        item_id = item.id

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as s:
            yield s

    async def override_get_current_user() -> AppUser:
        return arp_user

    app.dependency_overrides[get_db_session] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user

    try:
        csrf_token = generate_csrf_token()
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport,
            base_url="http://testserver",
            cookies={"abhyas_csrf": csrf_token},
        ) as client:
            answer_text = "पहले 10-10 के बंडल बनवाएँ, फिर खुली तीलियाँ गिनवाएँ।"
            res = await client.post(
                "/arp/answer",
                data={
                    "csrf_token": csrf_token,
                    "question_id": str(q_id),
                    "answer_hi": answer_text,
                },
                follow_redirects=False,
            )
            assert res.status_code == 303
            assert "/arp?saved=1&msg=ans" in res.headers["location"]

        # Verify DB updates
        async with session_factory() as session:
            # 1. Question status
            updated_q = await session.get(Question, q_id)
            assert updated_q is not None
            assert updated_q.status == "arp_answered"
            assert updated_q.answer_hi == answer_text

            # 2. ReviewItem resolved
            updated_item = await session.get(ReviewItem, item_id)
            assert updated_item is not None
            assert updated_item.status == "resolved"
            assert updated_item.resolved_by == arp_user.id
            assert updated_item.resolution is not None

            # 3. Outbound Message row inserted for teacher
            msg_res = await session.scalars(
                select(Message).where(
                    Message.teacher_id == t_id,
                    Message.direction == "outbound",
                    Message.speaker == "arp",
                )
            )
            msg = msg_res.first()
            assert msg is not None
            assert msg.channel == "web"
            assert answer_text in (msg.text or "")
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_escalated_question_non_consenting_teacher_anonymised(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Escalated questions from non-consenting teachers must show anonymised identifier."""
    async with session_factory() as session:
        arp_user = AppUser(
            id=uuid4(),
            username=f"arp.test.{uuid4().hex[:6]}",
            password_hash="hash",
            role="arp",
            cluster_id="KNP-C01",
        )
        session.add(arp_user)

        t_non_consent = Teacher(
            id=uuid4(),
            name="गुमनाम_शिक्षिका",
            cluster_id="KNP-C01",
            consent_share_scores=False,
            is_demo=False,
        )
        session.add(t_non_consent)

        q = Question(
            id=uuid4(),
            teacher_id=t_non_consent.id,
            text="कक्षा 2 में जोड़ सिखाने में कठिनाई हो रही है।",
            status="escalated",
        )
        session.add(q)
        await session.commit()

        digest = await build_arp_digest(session, arp_user)
        assert len(digest.escalated_questions) >= 1
        q_item = [item for item in digest.escalated_questions if item.question_id == str(q.id)][0]

        # Name must be anonymised code, never real name
        assert "गुमनाम_शिक्षिका" not in q_item.teacher_display_name
        assert q_item.teacher_display_name.startswith("शिक्षक #")
