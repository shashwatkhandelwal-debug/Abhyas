"""Integration tests for WhatsApp channel and webhook processing (spec/07 §7.2, T28).

Runs against real PostgreSQL in CI when TEST_DATABASE_URL is set.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from backend.app.channels.whatsapp.channel import WhatsAppChannel
from backend.app.channels.whatsapp.templates import load_whatsapp_templates
from backend.app.channels.whatsapp.webhook import (
    _dispatch_inbound_message,
    set_whatsapp_session_factory,
)
from backend.app.config import settings
from backend.app.core.types import Button, OutboundMessage
from backend.app.db.base import Base
from backend.app.db.models import Message, Teacher, TeacherContact, TemplateSend
from backend.app.privacy.hashing import (
    decrypt_phone_number,
    encrypt_phone_number,
    hash_phone_number,
)

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
async def db_session() -> AsyncIterator[AsyncSession]:
    assert TEST_DATABASE_URL is not None
    engine = create_async_engine(_async_url(TEST_DATABASE_URL), poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    async with session_maker() as session:
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_inbound_webhook_teacher_creation_and_persistence(db_session: AsyncSession) -> None:
    """Verifies that an inbound WhatsApp message creates teacher, contact, and message rows."""
    set_whatsapp_session_factory(lambda: db_session)
    phone = "+919876543299"
    msg_id = f"wamid.test.{uuid.uuid4()}"

    raw_msg = {
        "id": msg_id,
        "from": phone,
        "type": "text",
        "text": {"body": "नमस्ते अभ्यास"},
    }

    await _dispatch_inbound_message(raw_msg)

    # 1. Verify teacher was created with salted SHA-256 hash
    p_hash = hash_phone_number(phone)
    t_stmt = select(Teacher).where(Teacher.phone_hash == p_hash)
    teacher = (await db_session.execute(t_stmt)).scalar_one_or_none()
    assert teacher is not None
    assert teacher.preferred_channel == "whatsapp"
    assert teacher.onboarding_state == "NEW"

    # 2. Verify encrypted phone contact
    c_stmt = select(TeacherContact).where(TeacherContact.teacher_id == teacher.id)
    contact = (await db_session.execute(c_stmt)).scalar_one_or_none()
    assert contact is not None
    assert decrypt_phone_number(contact.phone_enc) == phone

    # 3. Verify inbound message was persisted
    m_stmt = select(Message).where(Message.channel_msg_id == msg_id)
    msg = (await db_session.execute(m_stmt)).scalar_one_or_none()
    assert msg is not None
    assert msg.direction == "in"
    assert msg.channel == "whatsapp"
    assert msg.text == "नमस्ते अभ्यास"


@pytest.mark.asyncio
async def test_inbound_deduplication(db_session: AsyncSession) -> None:
    """Duplicate message ID must not create duplicate Message rows."""
    set_whatsapp_session_factory(lambda: db_session)
    phone = "+919876543288"
    msg_id = f"wamid.dup.{uuid.uuid4()}"

    raw_msg = {
        "id": msg_id,
        "from": phone,
        "type": "text",
        "text": {"body": "पहला संदेश"},
    }

    # Dispatch twice
    await _dispatch_inbound_message(raw_msg)
    await _dispatch_inbound_message(raw_msg)

    m_stmt = select(Message).where(Message.channel_msg_id == msg_id)
    messages = (await db_session.execute(m_stmt)).scalars().all()
    assert len(messages) == 1


@pytest.mark.asyncio
async def test_outbound_channel_send_inside_window(db_session: AsyncSession) -> None:
    """Outbound messages inside the 24h window are persisted as 'out' messages."""
    channel = WhatsAppChannel()
    now = datetime.now(UTC)
    phone = "+919876543277"

    # Create teacher within window
    teacher = Teacher(
        id=uuid.uuid4(),
        phone_hash=hash_phone_number(phone),
        preferred_channel="whatsapp",
        last_inbound_at=now - timedelta(hours=1),
        created_at=now,
    )
    contact = TeacherContact(
        teacher_id=teacher.id,
        phone_enc=encrypt_phone_number(phone),
    )
    db_session.add_all([teacher, contact])
    await db_session.commit()

    outbound = OutboundMessage(
        kind="text",
        text_hi="शाबाश! आपने बहुत अच्छा अभ्यास किया।",
        buttons=[Button(id="btn_continue", title_hi="आगे बढ़ें")],
        speaker="coach",
    )

    await channel.send(teacher, [outbound], session=db_session)

    m_stmt = select(Message).where(
        Message.teacher_id == teacher.id,
        Message.direction == "out",
        Message.channel == "whatsapp",
    )
    sent_msgs = (await db_session.execute(m_stmt)).scalars().all()
    assert len(sent_msgs) >= 1
    assert any("शाबाश" in (m.text or "") for m in sent_msgs)


@pytest.mark.asyncio
async def test_outbound_channel_send_outside_window_approved_template(
    db_session: AsyncSession,
) -> None:
    """Outbound template messages outside 24h window record in template_send table."""
    channel = WhatsAppChannel()
    now = datetime.now(UTC)
    phone = "+919876543266"

    # Teacher outside 24h window
    teacher = Teacher(
        id=uuid.uuid4(),
        phone_hash=hash_phone_number(phone),
        preferred_channel="whatsapp",
        last_inbound_at=now - timedelta(hours=36),
        created_at=now - timedelta(hours=48),
    )
    contact = TeacherContact(
        teacher_id=teacher.id,
        phone_enc=encrypt_phone_number(phone),
    )
    db_session.add_all([teacher, contact])
    await db_session.commit()

    # Mark a template as approved for test
    templates = load_whatsapp_templates()
    templates["abhyas_reminder"]["approved"] = True

    outbound = OutboundMessage(
        kind="text",
        text_hi="अभ्यास जारी रखें",
        template_name="abhyas_reminder",
    )

    await channel.send(teacher, [outbound], session=db_session)

    # Verify template_send record created with estimated cost
    ts_stmt = select(TemplateSend).where(
        TemplateSend.teacher_id == teacher.id,
        TemplateSend.template_name == "abhyas_reminder",
    )
    ts_record = (await db_session.execute(ts_stmt)).scalar_one_or_none()
    assert ts_record is not None
    assert ts_record.category == "UTILITY"
    assert float(ts_record.est_cost_inr or 0) == settings.WHATSAPP_UTILITY_COST_INR
