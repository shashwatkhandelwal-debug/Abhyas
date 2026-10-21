"""Integration test: TTSCache round-trip through the Postgres tts_audio table (spec/06 §6.3).

Live bug: TTSCache.get rolled back the session and then read the expired ORM attribute,
which lazy-loads outside the async greenlet ("greenlet_spawn has not been called"), so
GET /api/audio/<key>.ogg returned 404. Unit tests never hit this: they use use_db=False,
and outside production a DB error silently switched the cache to disk.
Skipped locally if TEST_DATABASE_URL is not set.
"""

import io
import os
import wave
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from backend.app.speech import cache as cache_mod
from backend.app.speech.cache import TTSCache

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
    """Empty throwaway database migrated to head; dropped afterwards."""
    db_name = f"abhyas_tts_{uuid4().hex[:10]}"
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
async def db_cache(
    migrated_db: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[TTSCache]:
    """TTSCache backed only by the throwaway database (disk cache off)."""
    engine = create_async_engine(_url(migrated_db, "postgresql+asyncpg"), poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr(cache_mod, "async_session_factory", factory)
    cache = TTSCache(cache_dir=tmp_path, use_db=True)
    cache.use_disk = False  # production behaviour: the database is the only store
    yield cache
    await engine.dispose()


def _wav(seconds: float = 0.5) -> bytes:
    out = io.BytesIO()
    with wave.open(out, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(22050)
        wf.writeframes(b"\x10\x00\xf0\xff" * int(22050 * seconds / 2))
    return out.getvalue()


def _stored_bytes(db_name: str, key: str) -> tuple[bytes, bytes]:
    engine = create_engine(_url(db_name, "postgresql+psycopg2"))
    try:
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT ogg, mp3 FROM tts_audio WHERE cache_key = :k"), {"k": key}
            ).one()
            return bytes(row.ogg), bytes(row.mp3)
    finally:
        engine.dispose()


@pytest.mark.asyncio
async def test_put_wav_then_get_round_trips_ogg_and_mp3(
    db_cache: TTSCache, migrated_db: str
) -> None:
    key = uuid4().hex * 2  # 64 hex chars, like compute_cache_key

    await db_cache.put_wav(key, _wav())
    stored_ogg, stored_mp3 = _stored_bytes(migrated_db, key)
    assert stored_ogg.startswith(b"OggS")
    assert len(stored_mp3) > 0

    got_ogg = await db_cache.get(key, "ogg")
    got_mp3 = await db_cache.get(key, "mp3")

    assert got_ogg == stored_ogg
    assert got_mp3 == stored_mp3
    assert await db_cache.has(key, "ogg") is True
    assert db_cache.use_db is True, "a DB error must not have switched the cache off"
    assert await db_cache.get("0" * 64, "ogg") is None
