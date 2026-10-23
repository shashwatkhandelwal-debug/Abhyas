"""UI language toggle (persisted per user, cookie before login) and on-demand translation."""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import IntegrityError

from backend.app.auth.csrf import verify_csrf_token
from backend.app.auth.guards import get_current_user
from backend.app.auth.passwords import hash_password
from backend.app.auth.rate_limit import (
    reset_login_rate_limits,
    reset_translate_rate_limits,
)
from backend.app.auth.router import router as auth_router
from backend.app.auth.session import SESSION_COOKIE_NAME
from backend.app.config import settings
from backend.app.core.messages import LANG_COOKIE_NAME, get_message
from backend.app.db.models import AppUser, Message, MessageTranslation, Teacher
from backend.app.db.session import get_db_session
from backend.app.llm.client import LLMUnavailable
from backend.app.llm.roles.translator import TranslationUnavailable, translate_to_english
from backend.app.web import chat_api
from backend.app.web.chat_api import router as chat_router
from backend.app.web.ui_lang import UiLangMiddleware
from backend.app.web.ui_lang import router as lang_router
from backend.tests.unit.test_teacher_pwa import (  # noqa: F401  (fixtures)
    mock_teacher,
    mock_teacher_id,
    teacher_pwa_app,
)

DEVANAGARI = re.compile("[ऀ-ॿ]")
PASSWORD = "abhyas-demo-2026"


def _strip_content_and_switch(html: str) -> str:
    """Remove chat message text (content, not chrome) and the language switch's own Hindi link."""
    html = re.sub(r'<p class="bubble-text">.*?</p>', "", html, flags=re.S)
    # sample utterances in data-text are what the teacher says to Hindi-speaking children
    html = re.sub(r'data-text="[^"]*"', "", html)
    html = re.sub(r'<a [^>]*lang="hi"[^>]*>.*?</a>', "", html, flags=re.S)
    return html


# ── bilingual pages ──────────────────────────────────────────────────────────


async def test_english_chat_page_has_no_devanagari_in_chrome(teacher_pwa_app: FastAPI) -> None:  # noqa: F811
    teacher_pwa_app.add_middleware(UiLangMiddleware)
    async with AsyncClient(
        transport=ASGITransport(app=teacher_pwa_app), base_url="http://test"
    ) as client:
        hindi = (await client.get("/teacher")).text
        english = (await client.get("/teacher", cookies={LANG_COOKIE_NAME: "en"})).text
    assert "अभ्यास" in hindi and '<html lang="hi">' in hindi  # Hindi stays the default
    assert '<html lang="en">' in english
    leftovers = DEVANAGARI.findall(_strip_content_and_switch(english))
    # teacher name / child pill names come from data and persona content, not catalog chrome
    chrome = re.sub(r'title="[^"]*"', "", _strip_content_and_switch(english))
    chrome = re.sub(r"<span class=\"child-pill[^>]*>.*?</span>", "", chrome, flags=re.S)
    chrome = re.sub(r"<title>.*?</title>", "", chrome, flags=re.S)
    assert not DEVANAGARI.search(chrome), (len(leftovers), DEVANAGARI.findall(chrome)[:20])
    assert "Log out" in english and "Type or speak here…" in english
    # the thread only has a system bubble, so no per-bubble Translate button is rendered
    assert 'class="translate-btn"' not in english
    # the strings chat.js receives are English too
    assert '"ui_chat_msg_sent": "Sent"' in english.replace("&#34;", '"')


async def test_english_login_page_and_language_links() -> None:
    app = FastAPI()
    app.include_router(auth_router)
    app.include_router(lang_router)
    app.add_middleware(UiLangMiddleware)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        hi = (await client.get("/login")).text
        en = (await client.get("/login", cookies={LANG_COOKIE_NAME: "en"})).text
    assert "लॉगिन करें" in hi and "Log in" not in hi
    assert "Log in" in en and "Username" in en and "Password" in en
    assert not DEVANAGARI.search(_strip_content_and_switch(en))
    assert 'href="/lang/hi?next=/login"' in en and 'href="/lang/en?next=/login"' in en
    assert 'name="ui_lang" value="en"' in en


# ── toggle persists across logout / login ────────────────────────────────────


def _auth_app(user: AppUser) -> tuple[FastAPI, AsyncMock]:
    app = FastAPI()
    app.include_router(auth_router)
    app.include_router(lang_router)
    app.add_middleware(UiLangMiddleware)
    db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = user  # same object every time = the "database row"
    db.execute.return_value = result
    app.dependency_overrides[get_db_session] = lambda: db
    return app, db


def _teacher_user() -> AppUser:
    return AppUser(
        id=uuid.uuid4(),
        username="teacher.demo1",
        password_hash=hash_password(PASSWORD),
        role="teacher",
        display_name="Test",
        teacher_id=uuid.uuid4(),
        ui_lang="hi",
    )


async def _login(client: AsyncClient, **extra: Any) -> Any:
    reset_login_rate_limits()
    return await client.post(
        "/login", json={"username": "teacher.demo1", "password": PASSWORD, **extra}
    )


async def test_language_choice_persists_across_logout_and_login() -> None:
    user = _teacher_user()
    app, db = _auth_app(user)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert (await _login(client)).status_code == 200
        assert client.cookies.get(LANG_COOKIE_NAME) == "hi"

        # switch to English while signed in: saved on the user and in the cookie
        res = await client.get("/lang/en?next=/teacher", follow_redirects=False)
        assert res.status_code == 303 and res.headers["location"] == "/teacher"
        assert user.ui_lang == "en"
        db.commit.assert_awaited()
        assert client.cookies.get(LANG_COOKIE_NAME) == "en"

        # log out: session gone, language cookie stays, login page is English
        await client.get("/logout", follow_redirects=False)
        assert client.cookies.get(SESSION_COOKIE_NAME) is None
        assert "Log in" in (await client.get("/login")).text

        # log in again: still English
        assert (await _login(client)).status_code == 200
        assert client.cookies.get(LANG_COOKIE_NAME) == "en" and user.ui_lang == "en"

    # a different browser (no cookie) picks the saved preference up at login
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as other:
        assert LANG_COOKIE_NAME not in other.cookies
        assert (await _login(other)).status_code == 200
        assert other.cookies.get(LANG_COOKIE_NAME) == "en"


async def test_login_page_choice_is_saved_to_the_user() -> None:
    user = _teacher_user()
    app, _db = _auth_app(user)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await _login(client, ui_lang="en")  # JSON login ignores ui_lang; form login uses it
        assert res.status_code == 200
        page = await client.get("/login")
        token = client.cookies.get("abhyas_csrf")
        assert token and 'name="ui_lang"' in page.text
        reset_login_rate_limits()
        res = await client.post(
            "/login",
            data={
                "username": "teacher.demo1",
                "password": PASSWORD,
                "csrf_token": token,
                "ui_lang": "en",
            },
            follow_redirects=False,
        )
    assert res.status_code == 303
    assert user.ui_lang == "en"
    assert LANG_COOKIE_NAME in res.headers.get("set-cookie", "")


async def test_lang_endpoint_rejects_open_redirects_and_unknown_codes() -> None:
    user = _teacher_user()
    app, _db = _auth_app(user)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/lang/en?next=https://evil.example/x", follow_redirects=False)
        assert res.headers["location"] == "/"
        res = await client.get("/lang/en?next=//evil.example", follow_redirects=False)
        assert res.headers["location"] == "/"
        res = await client.get("/lang/klingon?next=/arp", follow_redirects=False)
        assert res.headers["location"] == "/arp"
        assert client.cookies.get(LANG_COOKIE_NAME) == "hi"  # unknown code falls back to Hindi


# ── translate endpoint ───────────────────────────────────────────────────────


class FakeDB:
    """Just enough of AsyncSession for the translate endpoint: get / add / commit / rollback."""

    def __init__(self, messages: list[Message]) -> None:
        self.messages = {m.id: m for m in messages}
        self.translations: dict[tuple[uuid.UUID, str], MessageTranslation] = {}
        self.commit_error: Exception | None = None

    async def get(self, model: Any, ident: Any) -> Any:
        if model is Message:
            return self.messages.get(ident)
        if model is MessageTranslation:
            return self.translations.get(ident)
        return None

    def add(self, obj: Any) -> None:
        if isinstance(obj, MessageTranslation):
            self._pending = obj

    async def commit(self) -> None:
        if self.commit_error is not None:
            err, self.commit_error = self.commit_error, None
            raise err
        obj = self._pending
        self.translations[(obj.message_id, obj.lang)] = obj

    async def rollback(self) -> None:
        return None


def _msg(
    teacher_id: uuid.UUID,
    speaker: str | None = "coach",
    text: str = "आपने बच्चे से 52 में से 17 पूछा।",
    direction: str = "out",
) -> Message:
    return Message(
        id=uuid.uuid4(),
        teacher_id=teacher_id,
        direction=direction,
        channel="web",
        channel_msg_id=str(uuid.uuid4()),
        kind="text",
        text=text,
        speaker=speaker,
        created_at=datetime.now(UTC),
    )


@pytest.fixture
def translate_env() -> Any:
    reset_translate_rate_limits()
    me = Teacher(id=uuid.uuid4(), name="Me", preferred_channel="web")
    other = Teacher(id=uuid.uuid4(), name="Other", preferred_channel="web")
    user = AppUser(
        id=uuid.uuid4(), username="t", role="teacher", teacher_id=me.id, password_hash="x"
    )
    mine = _msg(me.id)
    theirs = _msg(other.id)
    system_msg = _msg(me.id, speaker="abhyas")
    mine_in = _msg(me.id, speaker=None, direction="in")
    db = FakeDB([mine, theirs, system_msg, mine_in])
    app = FastAPI()
    app.include_router(chat_router)
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db_session] = lambda: db
    app.dependency_overrides[verify_csrf_token] = lambda: None
    with patch.object(chat_api, "get_teacher_for_user", AsyncMock(return_value=me)):
        yield app, db, {"mine": mine, "theirs": theirs, "system": system_msg, "inbound": mine_in}
    reset_translate_rate_limits()


async def _post(app: FastAPI, message_id: Any) -> Any:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        return await c.post("/api/chat/translate", json={"message_id": str(message_id)})


async def test_translate_caches_so_second_call_makes_no_llm_call(translate_env: Any) -> None:
    app, db, msgs = translate_env
    llm = AsyncMock(return_value="You asked the child 52 minus 17.")
    with patch.object(chat_api, "translate_to_english", llm):
        first = await _post(app, msgs["mine"].id)
        second = await _post(app, msgs["mine"].id)
    assert first.status_code == 200 and first.json() == {
        "text": "You asked the child 52 minus 17.",
        "cached": False,
    }
    assert second.status_code == 200 and second.json()["cached"] is True
    assert second.json()["text"] == first.json()["text"]
    assert llm.await_count == 1  # the second call never reached the LLM
    assert (msgs["mine"].id, "en") in db.translations
    assert msgs["mine"].text == "आपने बच्चे से 52 में से 17 पूछा।"  # Hindi untouched


async def test_translate_enforces_ownership_and_eligibility(translate_env: Any) -> None:
    app, _db, msgs = translate_env
    llm = AsyncMock(return_value="x")
    with patch.object(chat_api, "translate_to_english", llm):
        other_users = await _post(app, msgs["theirs"].id)
        missing = await _post(app, uuid.uuid4())
        system = await _post(app, msgs["system"].id)
        inbound = await _post(app, msgs["inbound"].id)
        bad_id = await _post(app, "not-a-uuid")
    assert other_users.status_code == 404  # someone else's message looks the same as a missing one
    assert missing.status_code == 404
    assert system.status_code == 400 and system.json()["detail"] == "not_translatable"
    assert inbound.status_code == 400
    assert bad_id.status_code == 422
    llm.assert_not_awaited()


async def test_translate_llm_failure_is_an_error_and_not_cached(translate_env: Any) -> None:
    app, db, msgs = translate_env
    boom = AsyncMock(side_effect=TranslationUnavailable("guard failed twice"))
    with patch.object(chat_api, "translate_to_english", boom):
        failed = await _post(app, msgs["mine"].id)
    assert failed.status_code == 502 and failed.json()["detail"] == "translation_failed"
    assert db.translations == {}
    ok = AsyncMock(return_value="Fine now.")
    with patch.object(chat_api, "translate_to_english", ok):
        retry = await _post(app, msgs["mine"].id)
    assert retry.status_code == 200 and retry.json()["text"] == "Fine now."


async def test_translate_is_rate_limited_but_cache_hits_are_free(translate_env: Any) -> None:
    app, db, msgs = translate_env
    limit = settings.TRANSLATE_MAX_REQUESTS_PER_MINUTE
    extra = [_msg(msgs["mine"].teacher_id, speaker="ravi") for _ in range(limit + 1)]
    for m in extra:
        db.messages[m.id] = m
    llm = AsyncMock(return_value="Ok.")
    with patch.object(chat_api, "translate_to_english", llm):
        codes = [(await _post(app, m.id)).status_code for m in extra]
        cached_again = await _post(app, extra[0].id)
    assert codes[:limit] == [200] * limit
    assert codes[limit] == 429
    assert cached_again.status_code == 200 and cached_again.json()["cached"] is True
    assert llm.await_count == limit


async def test_translate_concurrent_store_conflict_still_returns_text(translate_env: Any) -> None:
    app, db, msgs = translate_env
    db.commit_error = IntegrityError("insert", {}, Exception("duplicate key"))
    with patch.object(chat_api, "translate_to_english", AsyncMock(return_value="Same text.")):
        res = await _post(app, msgs["mine"].id)
    assert res.status_code == 200 and res.json()["text"] == "Same text."


# ── translator role: schema + guard + retry ──────────────────────────────────

SOURCE = "आपने बच्चे से पूछा कि 52 में से 17 कैसे घटाया।"


async def test_translator_returns_guarded_english() -> None:
    call = AsyncMock(return_value={"text_en": "You asked the child how 17 was taken from 52."})
    with patch("backend.app.llm.roles.translator.call_tool", call):
        out = await translate_to_english(SOURCE)
    assert out.startswith("You asked the child")
    assert call.await_count == 1
    assert call.await_args.kwargs["model"] == settings.CLAUDE_MODEL_FAST  # the fast model
    assert "<text>" in call.await_args.kwargs["messages"][0]["content"]


async def test_translator_guard_rejects_changed_numbers_then_retries() -> None:
    bad = {"text_en": "You asked the child how 18 was taken from 52."}  # 17 -> 18 changed
    good = {"text_en": "You asked the child how 17 was taken from 52."}
    call = AsyncMock(side_effect=[bad, good])
    with patch("backend.app.llm.roles.translator.call_tool", call):
        out = await translate_to_english(SOURCE)
    assert "17" in out and call.await_count == 2
    assert "failed validation" in call.await_args_list[1].kwargs["messages"][-1]["content"]


async def test_translator_gives_up_after_one_retry_and_on_unavailable_llm() -> None:
    hindi_left = {"text_en": "आपने बच्चे से 52 17 पूछा"}
    call = AsyncMock(side_effect=[hindi_left, hindi_left])
    with (
        patch("backend.app.llm.roles.translator.call_tool", call),
        pytest.raises(TranslationUnavailable),
    ):
        await translate_to_english(SOURCE)
    assert call.await_count == 2
    with (
        patch(
            "backend.app.llm.roles.translator.call_tool",
            AsyncMock(side_effect=LLMUnavailable("down")),
        ),
        pytest.raises(TranslationUnavailable),
    ):
        await translate_to_english(SOURCE)
    with pytest.raises(TranslationUnavailable):
        await translate_to_english("   ")


async def test_translator_mock_mode_returns_an_honest_placeholder() -> None:
    with patch.object(settings, "ANTHROPIC_API_KEY", ""):
        out = await translate_to_english(SOURCE)
    assert "Demo mode" in out


def test_translate_ui_strings_exist() -> None:
    assert get_message("ui_chat_translate", lang="en") == "Translate"
    assert get_message("speaker_guide", lang="en") == "Guide"
