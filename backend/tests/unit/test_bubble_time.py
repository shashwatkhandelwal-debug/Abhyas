"""fix3 K7: seeded and live bubbles show the clock the same way (12-hour with am/pm, local time)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from httpx import ASGITransport, AsyncClient

from backend.app.auth.guards import get_current_user
from backend.app.db.models import AppUser, Message, Teacher
from backend.app.db.session import get_db_session
from backend.app.web.teacher import STATIC_DIR
from backend.app.web.teacher import router as teacher_router


@pytest.mark.asyncio
async def test_server_rendered_bubble_time_is_12_hour_ist_and_carries_the_timestamp() -> None:
    app = FastAPI()
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    app.include_router(teacher_router)
    teacher_id = uuid.UUID("00000000-0000-0000-0000-000000000002")
    user = AppUser(
        id=uuid.uuid4(),
        username="teacher.demo2",
        role="teacher",
        teacher_id=teacher_id,
        password_hash="h",
        is_demo=True,
    )
    teacher = Teacher(
        id=teacher_id, name="अनीता", preferred_channel="web", is_demo=True,
        start_seen_at=datetime.now(UTC),
    )  # fmt: skip
    seeded = Message(
        id=uuid.uuid4(),
        teacher_id=teacher_id,
        direction="out",
        channel="web",
        channel_msg_id="seed-1",
        kind="text",
        text="नमस्ते",
        created_at=datetime(2026, 10, 30, 12, 26, tzinfo=UTC),  # 17:56 in India
    )
    db = MagicMock()
    db.get = AsyncMock(return_value=teacher)
    res = MagicMock()
    res.scalars.return_value.all.return_value = [seeded]
    res.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(return_value=res)
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db_session] = lambda: db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        html = (await client.get("/teacher")).text
    assert '<span class="msg-time" data-ts="2026-10-30T12:26:00+00:00">05:56 pm</span>' in html, (
        "12-hour India time with am/pm, not UTC 24-hour"
    )


def test_the_page_script_formats_every_bubble_with_one_function() -> None:
    js = (STATIC_DIR / "chat.js").read_text(encoding="utf-8")
    assert js.count("toLocaleTimeString") == 1  # the one shared formatter
    assert "localizeServerTimes(container)" in js
