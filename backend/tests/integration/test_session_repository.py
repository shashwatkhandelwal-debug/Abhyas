"""Integration tests for real SessionRepository against PostgreSQL (§14 T03, spec/08 §8.2).

Tests:
a) get_or_create_teacher and get_or_create_session_state idempotency, including a forced
   IntegrityError race condition handled via begin_nested() savepoints on two AsyncSessions.
b) Consent log and teacher flags round-trip persistence.
c) Second-instance continuity: service1 advances to REHEARSE (persisting child_states,
   rehearsal_turns_count, and prior_state_before_delete in JSONB), then a new SessionService
   on a fresh AsyncSession loads and continues the scene from the database alone.

Skipped locally if TEST_DATABASE_URL is not set.
"""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from backend.app.core.types import InboundMessage
from backend.app.db.models import Batch, Cluster, SessionState, Teacher
from backend.app.sessions.repository import SessionRepository
from backend.app.sessions.service import SessionService
from backend.app.sessions.state_machine import OnboardingStateEnum, SessionStateEnum

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
        await session.merge(Cluster(id="KNP-C01", name="Test Cluster"))
        await session.merge(Batch(id="KNP-B1", name="Test Batch"))
        await session.commit()
    try:
        yield factory
    finally:
        await engine.dispose()


def make_inbound(
    teacher_id: UUID | str,
    text: str | None = None,
    button_id: str | None = None,
) -> InboundMessage:
    return InboundMessage(
        channel="whatsapp",
        channel_msg_id=f"msg-{uuid4().hex[:8]}",
        teacher_id=teacher_id,
        kind="button" if button_id else "text",
        text=text,
        button_id=button_id,
        received_at=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_get_or_create_idempotent_and_integrity_error_race(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Verifies get_or_create methods are idempotent and recover gracefully from
    IntegrityError race conditions across concurrent sessions using savepoints."""
    teacher_id = uuid4()
    today = datetime.now(UTC).date()
    move_id = "NUM_PLACE_VALUE_BUNDLES"
    race_teacher_id = uuid4()

    try:
        # 1. Idempotency on get_or_create_teacher
        async with session_factory() as session1:
            repo1 = SessionRepository(session1)
            t1 = await repo1.get_or_create_teacher(teacher_id)
            assert t1.id == teacher_id
            assert t1.onboarding_state == "NEW"

        async with session_factory() as session2:
            repo2 = SessionRepository(session2)
            t2 = await repo2.get_or_create_teacher(teacher_id)
            assert t2.id == teacher_id

        # 2. Idempotency on get_or_create_session_state
        async with session_factory() as session1:
            repo1 = SessionRepository(session1)
            st1 = await repo1.get_or_create_session_state(teacher_id, today, move_id)
            assert st1.teacher_id == teacher_id
            assert st1.week_start == today
            assert st1.move_id == move_id

        async with session_factory() as session2:
            repo2 = SessionRepository(session2)
            st2 = await repo2.get_or_create_session_state(teacher_id, today, move_id)
            assert st2.teacher_id == teacher_id
            assert st2.week_start == today

        # 3. Forced IntegrityError race on teacher creation
        # Session B commits the record first
        async with session_factory() as session_b:
            tb = Teacher(
                id=race_teacher_id,
                onboarding_state="NEW",
                address_form="m",
                created_at=datetime.now(UTC),
            )
            session_b.add(tb)
            await session_b.commit()

        # Session A tries get_or_create, but its initial select query returns None
        async with session_factory() as session_a:
            repo_a = SessionRepository(session_a)
            real_exec = session_a.execute
            first_select_seen = False

            async def execute_mock(stmt: Any, *args: Any, **kwargs: Any) -> Any:
                nonlocal first_select_seen
                stmt_str = str(stmt).upper()
                if not first_select_seen and "SELECT" in stmt_str and "TEACHER" in stmt_str:
                    first_select_seen = True
                    mock_res = MagicMock()
                    mock_res.scalar_one_or_none.return_value = None
                    return mock_res
                return await real_exec(stmt, *args, **kwargs)

            session_a.execute = execute_mock  # type: ignore[method-assign]
            # Catches IntegrityError on insert, rolls back savepoint, re-selects, and succeeds
            res_t = await repo_a.get_or_create_teacher(race_teacher_id)
            assert res_t.id == race_teacher_id

        # 4. Forced IntegrityError race on session state creation
        race_week = today
        # Session B commits session state first
        async with session_factory() as session_b:
            stb = SessionState(
                teacher_id=race_teacher_id,
                week_start=race_week,
                move_id="m_race",
                state="LEARN",
                rehearse_attempts=0,
                context={},
                updated_at=datetime.now(UTC),
            )
            session_b.add(stb)
            await session_b.commit()

        # Session A simulates racing check
        async with session_factory() as session_a:
            repo_a = SessionRepository(session_a)
            real_exec = session_a.execute
            first_select_seen = False

            async def execute_mock_st(stmt: Any, *args: Any, **kwargs: Any) -> Any:
                nonlocal first_select_seen
                stmt_str = str(stmt).upper()
                if not first_select_seen and "SELECT" in stmt_str and "SESSION_STATE" in stmt_str:
                    first_select_seen = True
                    mock_res = MagicMock()
                    mock_res.scalar_one_or_none.return_value = None
                    return mock_res
                return await real_exec(stmt, *args, **kwargs)

            session_a.execute = execute_mock_st  # type: ignore[method-assign]
            res_st = await repo_a.get_or_create_session_state(race_teacher_id, race_week, "m_race")
            assert res_st.teacher_id == race_teacher_id
            assert res_st.week_start == race_week
    finally:
        # Cleanup
        async with session_factory() as session_clean:
            repo_clean = SessionRepository(session_clean)
            await repo_clean.purge_teacher_data(teacher_id)
            await repo_clean.purge_teacher_data(race_teacher_id)


@pytest.mark.asyncio
async def test_consent_log_and_teacher_flags_round_trip(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Verifies consent logging and teacher profile flags round-trip to PostgreSQL."""
    teacher_id = uuid4()
    try:
        async with session_factory() as session1:
            repo1 = SessionRepository(session1)
            t = await repo1.get_or_create_teacher(teacher_id)
            t.consent_service = True
            t.consent_share_scores = True
            t.name = "Sanjay Verma"
            t.address_form = "m"
            t.onboarding_state = "READY"
            t.cluster_id = "KNP-C01"
            await repo1.save_teacher(t)

            log_entry = await repo1.log_consent(
                teacher_id=teacher_id, field="consent_service", value=True, channel="whatsapp"
            )
            assert log_entry.teacher_id == teacher_id
            assert log_entry.field == "consent_service"
            assert log_entry.value is True

        # Fresh session verification
        async with session_factory() as session2:
            repo2 = SessionRepository(session2)
            loaded = await repo2.get_or_create_teacher(teacher_id)
            assert loaded.consent_service is True
            assert loaded.consent_share_scores is True
            assert loaded.name == "Sanjay Verma"
            assert loaded.address_form == "m"
            assert loaded.onboarding_state == "READY"
            assert loaded.cluster_id == "KNP-C01"
    finally:
        async with session_factory() as session_clean:
            repo_clean = SessionRepository(session_clean)
            await repo_clean.purge_teacher_data(teacher_id)


@pytest.mark.asyncio
async def test_second_instance_continuity_mid_scene_real_db(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Verifies a second SessionService instance on a fresh AsyncSession loads and continues
    a session mid-scene from PostgreSQL JSONB context alone."""
    teacher_id = uuid4()
    try:
        # Instance 1: advances context to REHEARSE and sets scene state
        async with session_factory() as session1:
            repo1 = SessionRepository(session1)
            service1 = SessionService(repository=repo1)
            ctx1 = await service1.get_or_create_context(teacher_id)
            ctx1.onboarding_state = OnboardingStateEnum.READY
            ctx1.current_state = SessionStateEnum.REHEARSE
            ctx1.rehearsal_turns_count = 2
            ctx1.prior_state_before_delete = SessionStateEnum.REHEARSE
            ctx1.child_states = {"ravi": 1}
            await service1._sync_context_to_db(ctx1, teacher_id)

        # Instance 2: completely new SessionService and AsyncSession
        async with session_factory() as session2:
            repo2 = SessionRepository(session2)
            service2 = SessionService(repository=repo2)
            ctx2 = await service2.get_or_create_context(teacher_id)

            # Assert state deserialized faithfully from DB JSONB
            assert ctx2.current_state == SessionStateEnum.REHEARSE
            assert ctx2.rehearsal_turns_count == 2
            assert ctx2.prior_state_before_delete == SessionStateEnum.REHEARSE
            assert ctx2.child_states == {"ravi": 1}

            # Handle teacher turn 3 in the second service instance
            out = await service2.handle_inbound(
                make_inbound(
                    teacher_id=teacher_id,
                    text="turn 3 test inbound",
                )
            )
            assert len(out) >= 1

            # Verify updated turn count persisted in DB
            ctx2_updated = await service2.get_or_create_context(teacher_id)
            assert ctx2_updated.current_state == SessionStateEnum.REHEARSE
            assert ctx2_updated.rehearsal_turns_count == 3
    finally:
        async with session_factory() as session_clean:
            repo_clean = SessionRepository(session_clean)
            await repo_clean.purge_teacher_data(teacher_id)
