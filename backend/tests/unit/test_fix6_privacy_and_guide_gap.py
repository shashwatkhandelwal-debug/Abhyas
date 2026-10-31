"""fix6: the offline copy of the chat belongs to one account; no gap in a Guide reply."""

from __future__ import annotations

import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from test_auth import auth_app  # noqa: F401

from backend.app.auth.passwords import hash_password
from backend.app.auth.session import (
    SESSION_COOKIE_NAME,
    USER_COOKIE_NAME,
    clear_session_cookie,
    create_session_token,
    set_session_cookie,
)
from backend.app.core.outbound_text import tidy_blank_lines
from backend.app.db.models import AppUser
from backend.app.db.session import get_db_session
from backend.app.llm.roles.guide_answerer import GuideAnswererOutput, compose_guide_reply
from backend.app.retrieval.search import RetrievedChunk

STATIC = Path(__file__).parents[2] / "app" / "web" / "static"
OFFLINE = Path(__file__).parents[2] / "app" / "web" / "templates" / "offline.html"

# the live string from the hosted app: six newlines between the bullets and the tip
LIVE_GUIDE = "...सीखने के मौके तैयार करें।\n\n\n\n\n\nइस हफ्ते आज़माएँ: कुछ करें"


# ── 1. privacy: which account owns the offline copy ─────────────────────────────────────────
@pytest.mark.asyncio
async def test_login_sets_a_readable_user_cookie_and_logout_removes_it(
    auth_app: FastAPI,  # noqa: F811
) -> None:
    user_id = uuid.uuid4()
    user = AppUser(
        id=user_id,
        username="teacher.demo2",
        password_hash=hash_password("abhyas-demo-2026"),
        role="teacher",
        display_name="d2",
        teacher_id=uuid.uuid4(),
    )
    result = MagicMock()
    result.scalar_one_or_none.return_value = user
    db = AsyncMock()
    db.execute.return_value = result
    auth_app.dependency_overrides[get_db_session] = lambda: db
    try:
        async with AsyncClient(
            transport=ASGITransport(app=auth_app), base_url="http://test"
        ) as client:
            res = await client.post(
                "/login", json={"username": "teacher.demo2", "password": "abhyas-demo-2026"}
            )
            assert res.status_code == 200
            assert res.cookies[USER_COOKIE_NAME] == str(user_id)
            set_cookie = [h for h in res.headers.get_list("set-cookie") if USER_COOKIE_NAME in h]
            assert set_cookie and "httponly" not in set_cookie[0].lower()  # the page must read it
            out = await client.post("/logout", headers={"Accept": "application/json"})
            cleared = [h for h in out.headers.get_list("set-cookie") if USER_COOKIE_NAME in h]
            assert cleared and "max-age=0" in cleared[0].lower()
    finally:
        auth_app.dependency_overrides.clear()


def test_every_logout_path_uses_the_one_clearing_function() -> None:
    from starlette.responses import Response

    resp = Response()
    set_session_cookie(resp, create_session_token({"user_id": "u-1"}))
    names = [h.decode().split("=")[0] for k, h in resp.raw_headers if k == b"set-cookie"]
    assert names == [SESSION_COOKIE_NAME, USER_COOKIE_NAME]
    gone = Response()
    clear_session_cookie(gone)
    text = " ".join(h.decode() for k, h in gone.raw_headers if k == b"set-cookie")
    assert SESSION_COOKIE_NAME in text and USER_COOKIE_NAME in text


def test_offline_page_shows_only_the_current_accounts_rows() -> None:
    html = OFFLINE.read_text(encoding="utf-8")
    assert "abhyas_uid" in html
    assert ".filter((m) => m.uid === uid)" in html
    # no cookie (logged out): nothing matches, so the list is empty
    assert "|| '\0'" in html


def test_every_stored_row_is_tagged_and_read_back_by_account() -> None:
    js = (STATIC / "chat.js").read_text(encoding="utf-8")
    assert "(item.uid = myUid())" in js and "(m.uid = myUid())" in js
    assert ".filter((i) => i.uid === myUid())" in js
    assert "await syncAccount();" in js  # first thing on every chat page load
    for old in ("res.status === 401",):
        assert old in js  # session over: the local copy goes too


def test_service_worker_never_stores_chat_or_history_responses() -> None:
    sw = (STATIC / "sw.js").read_text(encoding="utf-8")
    assert "/api/chat" not in sw and "/teacher" not in sw and "/api/history" not in sw
    # the only page it keeps is the public login page; only audio and static files otherwise
    puts = [ln.strip() for ln in sw.splitlines() if "cache.put(" in ln or ".put(" in ln]
    assert all(("LOGIN_PAGE" in p) or ("event.request" in p) for p in puts), puts


# ── 3. Guide reply: no blank gap ───────────────────────────────────────────────────────────
def test_the_live_guide_string_collapses_to_one_blank_line() -> None:
    out = tidy_blank_lines(LIVE_GUIDE)
    assert "\n\n\n" not in out
    assert out == "...सीखने के मौके तैयार करें।\n\nइस हफ्ते आज़माएँ: कुछ करें"


def test_guide_reply_with_two_sources_and_a_tip_has_single_blank_lines() -> None:
    answer = GuideAnswererOutput(
        answer_hi="• एक\n• दो",
        source_ids=["c1", "c2"],
        confidence=0.9,
        try_this_week_hi="कुछ करें",
    )
    chunks = [
        RetrievedChunk(
            chunk_id=cid,
            source="s",
            section="x",
            text="t",
            similarity_score=0.9,
            source_short_hi=label,
            page=page,
        )
        for cid, label, page in (("c1", "मार्गदर्शिका", 4), ("c2", "हैंडबुक", 9), ("c3", "", None))
    ]
    answer.source_ids.append("c3")  # a source with no label used to leave an empty piece
    text = compose_guide_reply(answer, chunks, address_form="f")
    assert "\n\n\n" not in text and text.endswith("इस हफ्ते आज़माएँ: कुछ करें")


@pytest.mark.asyncio
async def test_web_channel_leaves_no_gap_where_citation_lines_were_removed() -> None:
    from backend.app.channels.web import WebChannel
    from backend.app.core.types import Citation, OutboundMessage
    from backend.app.db.models import Teacher

    c1 = "स्रोत: मार्गदर्शिका, पृष्ठ 4"
    c2 = "स्रोत: हैंडबुक, पृष्ठ 9"
    text = f"उत्तर यह है।\n\n{c1}\n\n{c2}\n\nइस हफ्ते आज़माएँ: कुछ करें"
    msg = OutboundMessage(
        kind="text",
        text_hi=text,
        speaker="guide",
        citations=[
            Citation(chunk_id="a", line_hi=c1, source_short_hi="x", page=4),
            Citation(chunk_id="b", line_hi=c2, source_short_hi="y", page=9),
        ],
    )
    session = AsyncMock()
    session.add = MagicMock()
    await WebChannel().send(Teacher(id=uuid.uuid4(), name="t"), [msg], session=session)
    stored = session.add.call_args.args[0].text
    assert stored == "उत्तर यह है।\n\nइस हफ्ते आज़माएँ: कुछ करें"
