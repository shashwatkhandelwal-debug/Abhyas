"""Integration test: a voice note whose STT transcript lands after the first poll is re-sent.

The PWA shows "आपकी आवाज़ को लिखा जा रहा है…" under the voice-note bubble and swaps in the
transcript when /api/chat/messages returns that row again. The poll used to re-send only rows
with an audio_ref, so the transcript never reached the browser. Skipped locally if
TEST_DATABASE_URL is not set.
"""

import os
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from starlette.requests import Request

from backend.app.db.models import AppUser, Message, Teacher
from backend.app.web.chat_api import get_chat_messages

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
REPO_ROOT = Path(__file__).resolve().parents[3]

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL not set (runs in CI with real pgvector/pgvector:pg16)",
)


def _url(db_name: str | None, driver: str) -> str:
    assert TEST_DATABASE_URL is not None
    url = make_url(TEST_DATABASE_URL).set(drivername=driver)
    if db_name is not None:
        url = url.set(database=db_name)
    return url.render_as_string(hide_password=False)


@pytest.fixture
def migrated_db() -> Iterator[str]:
    db_name = f"abhyas_poll_{uuid4().hex[:10]}"
    admin = create_engine(_url(None, "postgresql+psycopg2"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{db_name}"'))
    try:
        cfg = Config(str(REPO_ROOT / "alembic.ini"))
        cfg.set_main_option("script_location", str(REPO_ROOT / "backend/app/db/migrations"))
        cfg.set_main_option("sqlalchemy.url", _url(db_name, "postgresql"))
        command.upgrade(cfg, "head")
        yield db_name
    finally:
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{db_name}" WITH (FORCE)'))
        admin.dispose()


@pytest.fixture
async def session(migrated_db: str) -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(_url(migrated_db, "postgresql+asyncpg"), poolclass=NullPool)
    async with async_sessionmaker(engine, expire_on_commit=False)() as s:
        yield s
    await engine.dispose()


def _request() -> Request:
    return Request({"type": "http", "query_string": b"", "headers": [], "method": "GET"})


async def test_transcribed_voice_note_is_resent_once(session: AsyncSession) -> None:
    teacher = Teacher(id=uuid4(), name="टेस्ट", preferred_channel="web")
    user = AppUser(
        id=uuid4(), username="t.poll", role="teacher", teacher_id=teacher.id, password_hash="x"
    )
    session.add_all([teacher, user])
    await session.commit()

    t0 = datetime(2026, 10, 22, 9, 0, 0, tzinfo=UTC)
    bot = Message(
        id=uuid4(), teacher_id=teacher.id, direction="out", channel="web",
        channel_msg_id="bot-1", kind="text", text="नमस्ते", speaker="abhyas",
        created_at=t0, updated_at=t0,
    )  # fmt: skip
    voice_at = t0 + timedelta(seconds=10)
    voice = Message(
        id=uuid4(), teacher_id=teacher.id, direction="in", channel="web",
        channel_msg_id="client-voice", kind="audio", text=None,
        created_at=voice_at, updated_at=voice_at,
    )  # fmt: skip
    session.add_all([bot, voice])
    await session.commit()

    async def poll(after: Message, audio_since: datetime) -> list[dict[str, object]]:
        res = await get_chat_messages(
            current_user=user,
            db=session,
            request=_request(),
            after=str(after.id),
            audio_since=audio_since.isoformat(),
        )
        return list(res["messages"])

    # first poll (cursor = bot message): the voice note arrives, transcript not ready yet
    first = await poll(bot, t0 + timedelta(seconds=1))
    assert [m["id"] for m in first] == [str(voice.id)]
    assert first[0]["text"] is None and first[0]["client_msg_id"] == "client-voice"
    server_time_1 = voice_at + timedelta(seconds=1)

    # nothing changed: the next poll (cursor now = voice note) returns nothing
    assert await poll(voice, server_time_1) == []

    # STT finishes -> web.py sets text and bumps updated_at
    row = await session.get(Message, voice.id)
    assert row is not None
    row.text = "रवि, 52 में से 17 कैसे घटाया?"
    row.updated_at = voice_at + timedelta(seconds=3)
    await session.commit()

    again = await poll(voice, server_time_1)
    assert [m["id"] for m in again] == [str(voice.id)]
    assert again[0]["text"] == "रवि, 52 में से 17 कैसे घटाया?"

    # and only once: a poll whose audio_since is past the update no longer returns it
    assert await poll(voice, voice_at + timedelta(seconds=4)) == []
