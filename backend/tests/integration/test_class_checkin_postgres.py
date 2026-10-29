"""The check-in on PostgreSQL: stored once per tap sequence, constraint, purge, demo reset.

Skipped locally if TEST_DATABASE_URL is not set.
"""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from backend.app.class_profile import checkin_flow
from backend.app.config import settings
from backend.app.core.types import InboundMessage
from backend.app.db.base import Base
from backend.app.db.models import ClassCheckin
from backend.app.privacy.purge import purge_teacher_data
from backend.app.sessions.repository import SessionRepository
from backend.app.sessions.service import SessionService
from backend.app.sessions.state_machine import OnboardingStateEnum, SessionStateEnum

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL not set (runs in CI with real pgvector/pgvector:pg16)",
)


def _async_url() -> str:
    url = TEST_DATABASE_URL or ""
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url.replace("postgresql+psycopg2://", "postgresql+asyncpg://")


@pytest.fixture
async def session_factory() -> AsyncGenerator[async_sessionmaker[AsyncSession], None]:
    engine = create_async_engine(_async_url(), poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        yield factory
    finally:
        await engine.dispose()


def _tap(teacher_id: UUID, button: str) -> InboundMessage:
    return InboundMessage(
        channel="web",
        channel_msg_id=f"m-{uuid4().hex[:8]}",
        teacher_id=teacher_id,
        kind="button",
        text=None,
        button_id=button,
        received_at=datetime.now(UTC),
    )


async def _rows(session: AsyncSession, teacher_id: UUID) -> list[ClassCheckin]:
    res = await session.execute(select(ClassCheckin).where(ClassCheckin.teacher_id == teacher_id))
    return list(res.scalars().all())


@pytest.mark.asyncio
async def test_check_in_is_stored_once_and_purged_with_the_teacher(
    session_factory: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "CLASS_CHECKIN_ENABLED", True)
    teacher_id = uuid4()
    async with session_factory() as session:
        service = SessionService(db_session=session)
        ctx = await service.get_or_create_context(teacher_id)
        ctx.onboarding_state = OnboardingStateEnum.READY
        ctx.current_move_id = "NUM_SUB_REGROUP_BUNDLES"
        ctx.current_state = SessionStateEnum.DONE
        ctx.name = "परीक्षण"
        await service._sync_context_to_db(ctx, teacher_id)

        for button in (
            checkin_flow.BTN_START,
            f"{checkin_flow.MODULE_PREFIX}NUM_SUB_REGROUP_BUNDLES",
            "btn_chk_some",
            f"{checkin_flow.STRUGGLE_PREFIX}NUM_SUB_REGROUP",
            f"{checkin_flow.STRUGGLE_PREFIX}NUM_SUB_REGROUP",  # the same tap again
        ):
            await service.handle_inbound(_tap(teacher_id, button))
        [row] = await _rows(session, teacher_id)
        assert (row.module_id, row.outcome, row.struggle_ids) == (
            "NUM_SUB_REGROUP_BUNDLES",
            "some",
            ["NUM_SUB_REGROUP"],
        )

        # the repository itself also refuses the same check-in inside the window
        repo = SessionRepository(session)
        assert (
            await repo.record_class_checkin(
                teacher_id, "NUM_SUB_REGROUP_BUNDLES", "some", ["NUM_SUB_REGROUP"]
            )
            is None
        )
        # a different outcome is a new check-in
        assert await repo.record_class_checkin(teacher_id, "NUM_SUB_REGROUP_BUNDLES", "well", [])
        assert len(await _rows(session, teacher_id)) == 2

        await purge_teacher_data(session, teacher_id)
        await session.commit()
        assert await _rows(session, teacher_id) == []


@pytest.mark.asyncio
async def test_outcome_check_constraint_rejects_a_free_text_outcome(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    teacher_id = uuid4()
    async with session_factory() as session:
        await SessionService(db_session=session).get_or_create_context(teacher_id)
        session.add(
            ClassCheckin(
                teacher_id=teacher_id,
                module_id="LIT_MATRA_BLENDING",
                outcome="बहुत अच्छा",
                struggle_ids=[],
            )
        )
        with pytest.raises(IntegrityError):
            await session.commit()
