"""Integration tests for the end-of-week "rate the training" step against PostgreSQL.

Covers the conversation (rating by button / digit / spoken number, optional comment, skip), what is
stored in ``training_rating``, and the aggregate shown in the trainer view (own district, consenting
teachers, n<10 suppressed, no identity) and the admin dashboard. Skipped locally if
TEST_DATABASE_URL is not set.
"""

from __future__ import annotations

import os
import re
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from html import escape as html_escape
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from backend.app.auth.access import SUPPRESSION_MESSAGE
from backend.app.auth.guards import get_current_user
from backend.app.config import settings
from backend.app.core.messages import get_message
from backend.app.core.types import InboundMessage, OutboundMessage
from backend.app.db.base import Base
from backend.app.db.models import AppUser, Teacher, TrainingRating
from backend.app.db.session import get_db_session
from backend.app.main import app
from backend.app.sessions.repository import SessionRepository
from backend.app.sessions.service import SessionService
from backend.app.sessions.state_machine import OnboardingStateEnum, SessionStateEnum
from backend.app.sessions.training_rating import training_rating_summary

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


def _inbound(
    teacher_id: UUID, text_: str | None = None, button_id: str | None = None
) -> InboundMessage:
    return InboundMessage(
        channel="web",
        channel_msg_id=f"m-{uuid4().hex[:8]}",
        teacher_id=teacher_id,
        kind="button" if button_id else "text",
        text=text_,
        button_id=button_id,
        received_at=datetime.now(UTC),
    )


def _texts(out: list[OutboundMessage]) -> str:
    return "\n".join(m.text_hi or "" for m in out)


async def _teacher_at_end_of_reflection(
    service: SessionService, teacher_id: UUID, state: SessionStateEnum
) -> None:
    ctx = await service.get_or_create_context(teacher_id)
    ctx.onboarding_state = OnboardingStateEnum.READY
    ctx.current_move_id = "NUM_SUB_REGROUP_BUNDLES"
    ctx.current_state = state
    ctx.reflect_step = 3  # past the last checklist item / reflection question
    ctx.evidence_level = 1
    ctx.name = "परीक्षण"
    await service._sync_context_to_db(ctx, teacher_id)


async def _ratings(session: AsyncSession, teacher_id: UUID) -> list[TrainingRating]:
    res = await session.execute(
        select(TrainingRating).where(TrainingRating.teacher_id == teacher_id)
    )
    return list(res.scalars().all())


@pytest.mark.asyncio
async def test_rating_then_comment_after_self_reflection(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    teacher_id = uuid4()
    async with session_factory() as session:
        repo = SessionRepository(session)
        try:
            service = SessionService(repository=repo)
            await _teacher_at_end_of_reflection(service, teacher_id, SessionStateEnum.REFLECT_SELF)

            # finishing REFLECT asks for the rating instead of closing the week
            out = await service.handle_inbound(_inbound(teacher_id, "आज बहुत कुछ सीखा"))
            assert [b.id for b in out[0].buttons or []] == [
                "btn_trate_1",
                "btn_trate_3",
                "btn_trate_5",
            ]
            assert out[0].text_hi == get_message("rate_training_prompt", "f")
            assert "शाबाश" not in _texts(out)
            ctx = await service.get_or_create_context(teacher_id)
            assert ctx.rating_stage == "rating" and ctx.current_state == SessionStateEnum.DONE
            assert await _ratings(session, teacher_id) == []

            # not a rating: asked again, nothing stored
            out = await service.handle_inbound(_inbound(teacher_id, "बहुत अच्छा था"))
            assert out[0].text_hi == get_message("rate_training_unclear", "f")
            assert await _ratings(session, teacher_id) == []

            # a typed 4 (only the anchors 1/3/5 are buttons) stores it and asks for the comment
            out = await service.handle_inbound(_inbound(teacher_id, "4"))
            assert out[0].text_hi == get_message("rate_training_comment_prompt", "f")
            assert [b.id for b in out[0].buttons or []] == ["btn_trate_skip"]
            rows = await _ratings(session, teacher_id)
            assert [(r.rating, r.comment, r.move_id) for r in rows] == [
                (4, None, "NUM_SUB_REGROUP_BUNDLES")
            ]

            # the comment (typed, or the transcript of a voice note) is stored; the week closes
            comment = "बंडल वाला तरीका कक्षा में बहुत काम आया"
            out = await service.handle_inbound(_inbound(teacher_id, comment))
            assert _texts(out).startswith(get_message("rate_training_thanks", "f"))
            assert out[-1].buttons and out[-1].buttons[0].id == "btn_next_move"
            session.expire_all()
            assert [(r.rating, r.comment) for r in await _ratings(session, teacher_id)] == [
                (4, comment)
            ]
            ctx = await service.get_or_create_context(teacher_id)
            assert ctx.rating_stage == "" and ctx.current_state == SessionStateEnum.DONE
        finally:
            await repo.purge_teacher_data(teacher_id)


@pytest.mark.asyncio
async def test_spoken_rating_skip_and_peer_path(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    teacher_id = uuid4()
    async with session_factory() as session:
        repo = SessionRepository(session)
        try:
            service = SessionService(repository=repo)
            await _teacher_at_end_of_reflection(service, teacher_id, SessionStateEnum.REFLECT_PEER)
            await service.handle_inbound(_inbound(teacher_id, "checklist_done"))
            ctx = await service.get_or_create_context(teacher_id)
            assert ctx.rating_stage == "rating" and ctx.rating_level == 3

            # a voice note arrives as its transcript: "पाँच"
            await service.handle_inbound(_inbound(teacher_id, "पाँच"))
            out = await service.handle_inbound(_inbound(teacher_id, button_id="btn_trate_skip"))
            assert _texts(out).startswith(get_message("rate_training_thanks", "f"))
            session.expire_all()
            rows = await _ratings(session, teacher_id)
            assert [(r.rating, r.comment) for r in rows] == [(5, None)]
            assert (await service.get_or_create_context(teacher_id)).rating_stage == ""
        finally:
            await repo.purge_teacher_data(teacher_id)


@pytest.mark.asyncio
async def test_realism_rating_is_untouched(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """The FEEDBACK step still stores the realism rating in its own table."""
    teacher_id = uuid4()
    async with session_factory() as session:
        repo = SessionRepository(session)
        try:
            await repo.get_or_create_teacher(teacher_id)
            await repo.record_realism_rating(teacher_id=teacher_id, rating=3)
            assert await _ratings(session, teacher_id) == []  # not mixed into training_rating
        finally:
            await repo.purge_teacher_data(teacher_id)


async def _seed_ratings(
    session: AsyncSession,
    district: str,
    *,
    consenting: int,
    non_consenting: int = 0,
    rating: int = 4,
    comment: str | None = None,
) -> list[UUID]:
    ids: list[UUID] = []
    base = datetime.now(UTC)
    for i in range(consenting + non_consenting):
        t = Teacher(
            id=uuid4(),
            name=f"गुप्त_नाम_{i}",
            phone_hash=f"ph_{uuid4().hex}",
            district=district,
            consent_share_scores=i < consenting,
        )
        session.add(t)
        await session.flush()
        session.add(
            TrainingRating(
                teacher_id=t.id,
                rating=rating if i % 2 == 0 else 5,
                comment=f"{comment} {i}" if comment else None,
                created_at=base - timedelta(minutes=i),
            )
        )
        ids.append(t.id)
    await session.commit()
    return ids


async def _cleanup(factory: async_sessionmaker[AsyncSession], ids: list[UUID]) -> None:
    async with factory() as session:
        await session.execute(delete(Teacher).where(Teacher.id.in_(ids)))
        await session.commit()


@pytest.mark.asyncio
async def test_summary_average_count_latest_and_suppression(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    district = f"Test District {uuid4().hex[:8]}"
    async with session_factory() as session:
        ids = await _seed_ratings(session, district, consenting=12, comment="टिप्पणी")
        try:
            full = await training_rating_summary(session, district=district)
            assert full.count == 12 and not full.suppressed
            # six teachers rated 4, six rated 5
            assert full.average == pytest.approx(4.5)
            assert full.distribution == {4: 6, 5: 6}
            assert len(full.latest_comments) == settings.TRAINING_RATING_RECENT_COMMENTS
            assert full.latest_comments[0].comment == "टिप्पणी 0"  # newest first

            # n < 10 is withheld: only the count is returned
            small = await training_rating_summary(session, district=district, suppress_below=13)
            assert small.suppressed and small.count == 12
            assert small.average is None and small.latest_comments == []
            assert (
                await training_rating_summary(session, district=district, suppress_below=12)
            ).average == pytest.approx(4.5)

            # another district sees nothing of it
            other = await training_rating_summary(
                session, district="Elsewhere", consenting_only=True
            )
            assert other.count == 0 and other.average is None
        finally:
            await _cleanup(session_factory, ids)


@pytest.mark.asyncio
async def test_trainer_and_admin_views_show_the_aggregate_without_identity(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    district = f"Test District {uuid4().hex[:8]}"
    async with session_factory() as session:
        # 10 consenting teachers (shown), 3 who did not consent (never counted for the trainer)
        ids = await _seed_ratings(
            session, district, consenting=10, non_consenting=3, comment="अच्छा प्रशिक्षण"
        )
        small_district = f"Test District {uuid4().hex[:8]}"
        ids += await _seed_ratings(session, small_district, consenting=4, comment="छोटा समूह")

    async def real_db() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as s:
            yield s

    trainer = AppUser(
        id=uuid4(), username="trainer.test.x", password_hash="h", role="trainer", district=district
    )
    small_trainer = AppUser(
        id=uuid4(), username="trainer.test.y", password_hash="h", role="trainer",
        district=small_district,
    )  # fmt: skip
    admin = AppUser(id=uuid4(), username="admin.test.x", password_hash="h", role="admin")
    app.dependency_overrides[get_db_session] = real_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            app.dependency_overrides[get_current_user] = lambda: trainer
            res = await client.get("/trainer")
            assert res.status_code == 200, res.text[:300]
            html = res.text
            assert get_message("ui_ratings_title") in html
            # 10 consenting teachers, not the 3 others
            assert re.search(r'id="ratings-count"[^>]*>10<', html)
            assert 'id="ratings-average"' in html and "अच्छा प्रशिक्षण" in html
            assert "गुप्त_नाम" not in html and "ph_" not in html  # no identity

            # fewer than 10 ratings: count only, the n<10 notice instead of average and comments
            app.dependency_overrides[get_current_user] = lambda: small_trainer
            html = (await client.get("/trainer")).text
            assert html_escape(SUPPRESSION_MESSAGE) in html and "छोटा समूह" not in html
            assert 'id="ratings-average"' not in html

            # admin: everyone, no suppression
            app.dependency_overrides[get_current_user] = lambda: admin
            res = await client.get("/admin")
            assert res.status_code == 200, res.text[:300]
            assert get_message("ui_ratings_title") in res.text
            assert 'id="ratings-average"' in res.text
            assert "गुप्त_नाम" not in res.text
    finally:
        app.dependency_overrides.clear()
        await _cleanup(session_factory, ids)


@pytest.mark.asyncio
async def test_rating_unclear_twice_is_skipped_and_week_done_shown(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    teacher_id = uuid4()
    async with session_factory() as session:
        service = SessionService(repository=SessionRepository(session))
        await _teacher_at_end_of_reflection(service, teacher_id, SessionStateEnum.REFLECT_SELF)
        await service.handle_inbound(_inbound(teacher_id, "आज बहुत कुछ सीखा"))

        out = await service.handle_inbound(_inbound(teacher_id, "पता नहीं"))
        assert out[0].text_hi == get_message("rate_training_unclear", "f")
        out = await service.handle_inbound(_inbound(teacher_id, "कुछ भी"))
        assert get_message("rate_training_unclear", "f") not in _texts(out)
        assert out and out[0].buttons  # the week_done message with its buttons
        ctx = await service.get_or_create_context(teacher_id)
        assert ctx.rating_stage == "" and ctx.current_state == SessionStateEnum.DONE
        assert await _ratings(session, teacher_id) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("command", ["help", "progress", "next", "language"])
async def test_command_during_rating_clears_stage_and_is_processed(
    session_factory: async_sessionmaker[AsyncSession], command: str
) -> None:
    teacher_id = uuid4()
    async with session_factory() as session:
        service = SessionService(repository=SessionRepository(session))
        await _teacher_at_end_of_reflection(service, teacher_id, SessionStateEnum.REFLECT_SELF)
        await service.handle_inbound(_inbound(teacher_id, "आज बहुत कुछ सीखा"))

        out = await service.handle_inbound(_inbound(teacher_id, command))
        ctx = await service.get_or_create_context(teacher_id)
        assert ctx.rating_stage == ""
        assert await _ratings(session, teacher_id) == []
        assert get_message("rate_training_unclear", "f") not in _texts(out)
        assert get_message("rate_training_comment_prompt", "f") not in _texts(out)


@pytest.mark.asyncio
async def test_command_during_comment_clears_stage_and_is_processed(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    teacher_id = uuid4()
    async with session_factory() as session:
        service = SessionService(repository=SessionRepository(session))
        await _teacher_at_end_of_reflection(service, teacher_id, SessionStateEnum.REFLECT_SELF)
        await service.handle_inbound(_inbound(teacher_id, "आज बहुत कुछ सीखा"))
        await service.handle_inbound(_inbound(teacher_id, "4"))
        ctx = await service.get_or_create_context(teacher_id)
        assert ctx.rating_stage == "comment"

        out = await service.handle_inbound(_inbound(teacher_id, "help"))
        ctx = await service.get_or_create_context(teacher_id)
        assert ctx.rating_stage == ""
        assert get_message("rate_training_thanks", "f") not in _texts(out)
        rows = await _ratings(session, teacher_id)
        assert [(r.rating, r.comment) for r in rows] == [(4, None)]  # rating kept, no comment
