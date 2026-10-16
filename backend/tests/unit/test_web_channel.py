"""Unit tests for Web channel API, polling, idempotency, and audio caching (spec/07 §7.3, T26)."""

import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.auth.csrf import (
    CSRF_COOKIE_NAME,
    CSRF_HEADER_NAME,
    generate_csrf_token,
    verify_csrf_token,
)
from backend.app.auth.guards import get_current_user
from backend.app.channels.web import (
    WebChannel,
    get_teacher_lock,
    is_teacher_pending,
    mark_teacher_pending,
    process_inbound_web,
    reset_web_channel_state,
    set_channel_session_factory,
    set_conversation_service_factory,
    set_session_service_factory,
    unmark_teacher_pending,
)
from backend.app.config import settings
from backend.app.core.conversation import ConversationService
from backend.app.core.types import Button, InboundMessage, OutboundMessage
from backend.app.db.models import AppUser, Message, RealismRating, Teacher
from backend.app.db.session import get_db_session
from backend.app.sessions.service import SessionService
from backend.app.speech.cache import tts_cache
from backend.app.web.chat_api import router as chat_router
from backend.tests.unit.test_state_machine import FakeSessionRepository

# ── Test Fixtures ────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def clean_web_state() -> None:
    reset_web_channel_state()


@pytest.fixture
def mock_teacher_id() -> uuid.UUID:
    return uuid.UUID("00000000-0000-0000-0000-000000000002")


@pytest.fixture
def mock_user(mock_teacher_id: uuid.UUID) -> AppUser:
    return AppUser(
        id=uuid.uuid4(),
        username="teacher.demo2",
        role="teacher",
        teacher_id=mock_teacher_id,
        display_name="डेमो शिक्षिका 2",
        password_hash="hash",
    )


@pytest.fixture
def mock_teacher(mock_teacher_id: uuid.UUID) -> Teacher:
    return Teacher(
        id=mock_teacher_id,
        name="डेमो शिक्षिका 2 (अनीता)",
        preferred_channel="web",
        lite_mode=False,
    )


@pytest.fixture
def web_test_app(mock_user: AppUser, mock_teacher: Teacher) -> FastAPI:
    app = FastAPI()
    app.include_router(chat_router)

    # In-memory storage mock
    messages_db: dict[uuid.UUID, Message] = {}
    ratings_db: list[RealismRating] = []

    async def mock_get_current_user() -> AppUser:
        return mock_user

    db = AsyncMock(spec=AsyncSession)
    db.__aenter__ = AsyncMock(return_value=db)
    db.__aexit__ = AsyncMock(return_value=None)

    async def get_mock(entity: Any, ident: Any) -> Any:
        if entity is Teacher and ident == mock_teacher.id:
            return mock_teacher
        if entity is Message:
            return messages_db.get(ident)
        return None

    def add_mock(instance: Any) -> None:
        if isinstance(instance, Message):
            messages_db[instance.id] = instance
        elif isinstance(instance, RealismRating):
            ratings_db.append(instance)

    async def execute_mock(stmt: Any) -> Any:
        mock_res = MagicMock()
        str_stmt = str(stmt)
        if "FROM message" in str_stmt:
            # Check channel_msg_id dedupe via parameters
            params = list(getattr(stmt.compile(), "params", {}).values())
            matched = None
            for p in params:
                for msg in messages_db.values():
                    if msg.channel_msg_id == p:
                        matched = msg
                        break
                if matched:
                    break

            if matched:
                mock_res.scalar_one_or_none.return_value = matched
                mock_res.scalars.return_value.all.return_value = [matched]
                return mock_res

            all_msgs = sorted(
                messages_db.values(),
                key=lambda m: m.created_at or datetime.min.replace(tzinfo=UTC),
            )
            # Check if after cursor timestamp is present in params
            dt_param = next((p for p in params if isinstance(p, datetime)), None)
            after_id_param = next(
                (p for p in params if isinstance(p, uuid.UUID) and p != mock_teacher.id), None
            )
            if dt_param:
                filtered_msgs = [
                    m
                    for m in all_msgs
                    if m.created_at
                    and (
                        m.created_at > dt_param
                        or (m.created_at == dt_param and after_id_param and m.id != after_id_param)
                    )
                ]
                mock_res.scalars.return_value.all.return_value = filtered_msgs
            else:
                mock_res.scalars.return_value.all.return_value = all_msgs
            mock_res.scalar_one_or_none.return_value = None
        elif "FROM teacher" in str_stmt:
            mock_res.scalar_one_or_none.return_value = mock_teacher
        else:
            mock_res.scalar_one_or_none.return_value = None
            mock_res.scalars.return_value.all.return_value = []
        return mock_res

    db.get.side_effect = get_mock
    db.add.side_effect = add_mock
    db.execute.side_effect = execute_mock
    db.commit = AsyncMock()

    async def mock_db_session() -> AsyncSession:
        return db

    app.dependency_overrides[get_current_user] = mock_get_current_user
    app.dependency_overrides[get_db_session] = mock_db_session
    app.dependency_overrides[verify_csrf_token] = lambda: None

    set_channel_session_factory(lambda: db)
    app.state.messages_db = messages_db
    app.state.ratings_db = ratings_db

    return app


# ── Tests ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_send_chat_text_success_and_idempotency(web_test_app: FastAPI) -> None:
    client_msg_id = str(uuid.uuid4())

    async with AsyncClient(
        transport=ASGITransport(app=web_test_app), base_url="http://test"
    ) as client:
        # First submission
        res1 = await client.post(
            "/api/chat/text",
            json={"client_msg_id": client_msg_id, "text": "नमस्ते रवि, क्या तुमने बंडल बनाए?"},
        )
        assert res1.status_code == 202
        data1 = res1.json()
        assert data1["status"] == "accepted"
        msg_id1 = data1["message_id"]

        # Duplicate submission with same client_msg_id -> idempotency (§7.3)
        res2 = await client.post(
            "/api/chat/text",
            json={"client_msg_id": client_msg_id, "text": "नमस्ते रवि, क्या तुमने बंडल बनाए?"},
        )
        assert res2.status_code == 202
        data2 = res2.json()
        assert data2["status"] == "duplicate_ignored"
        assert data2["message_id"] == msg_id1


@pytest.mark.asyncio
async def test_send_chat_text_empty_validation(web_test_app: FastAPI) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=web_test_app), base_url="http://test"
    ) as client:
        res = await client.post(
            "/api/chat/text",
            json={"client_msg_id": str(uuid.uuid4()), "text": "   "},
        )
        assert res.status_code == 400


@pytest.mark.asyncio
async def test_send_chat_audio_upload_and_limit(web_test_app: FastAPI) -> None:
    client_msg_id = str(uuid.uuid4())
    dummy_audio = b"RIFF" + b"\x00" * 100

    async with AsyncClient(
        transport=ASGITransport(app=web_test_app), base_url="http://test"
    ) as client:
        # Normal audio <= 2 MB
        res = await client.post(
            "/api/chat/audio",
            data={"client_msg_id": client_msg_id},
            files={"file": ("voice.webm", dummy_audio, "audio/webm")},
        )
        assert res.status_code == 202
        data = res.json()
        assert data["status"] == "accepted"
        assert "message_id" in data

        # Oversized audio > 2 MB -> 413 (§7.3)
        oversized_audio = b"\x00" * (2 * 1024 * 1024 + 10)
        res_large = await client.post(
            "/api/chat/audio",
            data={"client_msg_id": str(uuid.uuid4())},
            files={"file": ("too_large.webm", oversized_audio, "audio/webm")},
        )
        assert res_large.status_code == 413

        # Empty audio -> 400
        res_empty = await client.post(
            "/api/chat/audio",
            data={"client_msg_id": str(uuid.uuid4())},
            files={"file": ("empty.webm", b"", "audio/webm")},
        )
        assert res_empty.status_code == 400


@pytest.mark.asyncio
async def test_send_chat_button_reply(web_test_app: FastAPI) -> None:
    client_msg_id = str(uuid.uuid4())

    async with AsyncClient(
        transport=ASGITransport(app=web_test_app), base_url="http://test"
    ) as client:
        res = await client.post(
            "/api/chat/button",
            json={"client_msg_id": client_msg_id, "button_id": "btn_start_rehearse"},
        )
        assert res.status_code == 202
        data = res.json()
        assert data["status"] == "accepted"
        assert "message_id" in data


@pytest.mark.asyncio
async def test_get_chat_messages_polling_and_pending_status(
    web_test_app: FastAPI,
    mock_teacher_id: uuid.UUID,
) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=web_test_app), base_url="http://test"
    ) as client:
        # Initial poll: not pending
        res1 = await client.get("/api/chat/messages")
        assert res1.status_code == 200
        data1 = res1.json()
        assert data1["pending"] is False

        # Mark pending (simulates background worker processing turn)
        mark_teacher_pending(mock_teacher_id)
        assert is_teacher_pending(mock_teacher_id) is True

        res2 = await client.get("/api/chat/messages")
        assert res2.status_code == 200
        data2 = res2.json()
        assert data2["pending"] is True

        # Unmark pending (worker finishes)
        unmark_teacher_pending(mock_teacher_id)
        assert is_teacher_pending(mock_teacher_id) is False

        res3 = await client.get("/api/chat/messages")
        assert res3.status_code == 200
        data3 = res3.json()
        assert data3["pending"] is False


@pytest.mark.asyncio
async def test_audio_cache_endpoint_headers(web_test_app: FastAPI) -> None:
    fixture_wav = Path(__file__).parents[1] / "fixtures" / "audio" / "sample_5s.wav"
    await tts_cache.put_wav("sample_voice_01", fixture_wav.read_bytes())

    async with AsyncClient(
        transport=ASGITransport(app=web_test_app), base_url="http://test"
    ) as client:
        res = await client.get("/api/audio/sample_voice_01.ogg")
        assert res.status_code == 200
        # Cache header required by §7.3
        cache_control = res.headers.get("cache-control", "")
        assert "private" in cache_control
        assert "max-age=31536000" in cache_control
        assert "immutable" in cache_control
        assert len(res.content) > 0


@pytest.mark.asyncio
async def test_post_chat_rating(web_test_app: FastAPI) -> None:
    scene_id = str(uuid.uuid4())

    async with AsyncClient(
        transport=ASGITransport(app=web_test_app), base_url="http://test"
    ) as client:
        # Valid rating (1-5)
        res_ok = await client.post(
            "/api/chat/rating",
            json={"scene_id": scene_id, "rating": 5},
        )
        assert res_ok.status_code == 200
        assert res_ok.json()["ok"] is True

        # Invalid rating 0
        res_low = await client.post(
            "/api/chat/rating",
            json={"scene_id": scene_id, "rating": 0},
        )
        assert res_low.status_code == 422  # Pydantic validation error ge=1

        # Invalid rating 6
        res_high = await client.post(
            "/api/chat/rating",
            json={"scene_id": scene_id, "rating": 6},
        )
        assert res_high.status_code == 422  # Pydantic validation error le=5


@pytest.mark.asyncio
async def test_update_settings_lite_mode(
    web_test_app: FastAPI,
    mock_teacher: Teacher,
) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=web_test_app), base_url="http://test"
    ) as client:
        res = await client.post("/api/settings", json={"lite_mode": True})
        assert res.status_code == 200
        data = res.json()
        assert data["ok"] is True
        assert data["lite_mode"] is True
        assert mock_teacher.lite_mode is True


def test_per_teacher_lock_identity() -> None:
    t1 = uuid.uuid4()
    t2 = uuid.uuid4()

    lock1_a = get_teacher_lock(t1)
    lock1_b = get_teacher_lock(t1)
    lock2 = get_teacher_lock(t2)

    assert lock1_a is lock1_b
    assert lock1_a is not lock2


@pytest.mark.asyncio
async def test_web_channel_send_persists_outbound() -> None:
    channel = WebChannel()
    teacher_id = uuid.uuid4()
    teacher = Teacher(id=teacher_id, name="शिक्षिका")

    msgs = [
        OutboundMessage(
            kind="text",
            text_hi="नमस्ते! आज का अभ्यास शुरू करते हैं।",
            speaker="abhyas",
        ),
        OutboundMessage(
            kind="buttons",
            text_hi="क्या आप तैयार हैं?",
            buttons=[Button(id="btn_ready", title_hi="हाँ, तैयार हूँ")],
        ),
    ]

    mock_session = AsyncMock(spec=AsyncSession)
    await channel.send(teacher, msgs, session=mock_session)

    assert mock_session.add.call_count == 2
    mock_session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_end_to_end_mock_conversation_flow(
    mock_teacher_id: uuid.UUID,
) -> None:
    # Test background process_inbound_web with a custom ConversationService mock
    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)
    mock_session.get.return_value = Teacher(id=mock_teacher_id, name="शिक्षिका")
    set_channel_session_factory(lambda: mock_session)

    class TestConversationService(ConversationService):
        async def handle(self, inbound: InboundMessage) -> list[OutboundMessage]:
            assert inbound.text == "रवि ने क्या कहा?"
            return [
                OutboundMessage(
                    kind="text",
                    text_hi="रवि ने कहा: मुझे समझ नहीं आया।",
                    speaker="ravi",
                )
            ]

    set_conversation_service_factory(TestConversationService)

    # Run background processing
    msg_id = uuid.uuid4()
    await process_inbound_web(
        teacher_id=mock_teacher_id,
        message_id=msg_id,
        kind="text",
        text="रवि ने क्या कहा?",
    )

    # Pending count must return to 0 after processing completes
    assert is_teacher_pending(mock_teacher_id) is False
    assert mock_session.add.call_count == 1


@pytest.mark.asyncio
async def test_e2e_text_submission_background_process_and_polling(
    web_test_app: FastAPI,
) -> None:
    """Tests text submission -> 202 -> background process -> polling returns bot outbound."""

    class FlowSessionService:
        async def handle_inbound(self, inbound: InboundMessage) -> list[OutboundMessage]:
            assert inbound.text == "नमस्ते, क्या हम शुरू करें?"
            return [
                OutboundMessage(
                    kind="text",
                    text_hi="हाँ, अभ्यास सत्र शुरू करते हैं।",
                    speaker="abhyas",
                )
            ]

    set_session_service_factory(lambda s: FlowSessionService())
    client_msg_id = str(uuid.uuid4())

    async with AsyncClient(
        transport=ASGITransport(app=web_test_app), base_url="http://test"
    ) as client:
        # 1. Post text message -> 202 accepted
        res = await client.post(
            "/api/chat/text",
            json={"client_msg_id": client_msg_id, "text": "नमस्ते, क्या हम शुरू करें?"},
        )
        assert res.status_code == 202
        data = res.json()
        assert data["status"] == "accepted"
        inbound_id = data["message_id"]

        # 2. Poll messages -> returns inbound message + bot outbound message
        res_poll = await client.get("/api/chat/messages")
        assert res_poll.status_code == 200
        poll_data = res_poll.json()
        assert poll_data["pending"] is False
        msgs = poll_data["messages"]
        assert len(msgs) == 2
        assert msgs[0]["direction"] == "in"
        assert msgs[0]["text"] == "नमस्ते, क्या हम शुरू करें?"
        assert msgs[1]["direction"] == "out"
        assert msgs[1]["text"] == "हाँ, अभ्यास सत्र शुरू करते हैं।"
        assert msgs[1]["speaker"] == "abhyas"

        # 3. Poll with after cursor -> returns only the bot outbound message
        res_after = await client.get(f"/api/chat/messages?after={inbound_id}")
        assert res_after.status_code == 200
        after_data = res_after.json()
        assert len(after_data["messages"]) == 1
        assert after_data["messages"][0]["direction"] == "out"


@pytest.mark.asyncio
async def test_e2e_duplicate_client_msg_id_no_reprocessing(
    web_test_app: FastAPI,
) -> None:
    """Duplicate client_msg_id returns existing message_id without extra processing."""
    call_count = 0

    class CountingSessionService:
        async def handle_inbound(self, inbound: InboundMessage) -> list[OutboundMessage]:
            nonlocal call_count
            call_count += 1
            return [OutboundMessage(kind="text", text_hi="प्रतिक्रिया", speaker="abhyas")]

    set_session_service_factory(lambda s: CountingSessionService())
    shared_id = str(uuid.uuid4())

    async with AsyncClient(
        transport=ASGITransport(app=web_test_app), base_url="http://test"
    ) as client:
        # First send
        res1 = await client.post(
            "/api/chat/text",
            json={"client_msg_id": shared_id, "text": "पहला अनुरोध"},
        )
        assert res1.status_code == 202
        assert res1.json()["status"] == "accepted"
        msg_id1 = res1.json()["message_id"]

        # Duplicate send
        res2 = await client.post(
            "/api/chat/text",
            json={"client_msg_id": shared_id, "text": "पहला अनुरोध"},
        )
        assert res2.status_code == 202
        assert res2.json()["status"] == "duplicate_ignored"
        assert res2.json()["message_id"] == msg_id1

        # Confirm handle_inbound only executed once
        assert call_count == 1


@pytest.mark.asyncio
async def test_e2e_audio_upload_with_mock_stt(
    web_test_app: FastAPI,
) -> None:
    """Audio upload invokes STT, records transcript, and runs SessionService."""
    recorded_transcript: str | None = None

    class AudioEchoService:
        async def handle_inbound(self, inbound: InboundMessage) -> list[OutboundMessage]:
            nonlocal recorded_transcript
            recorded_transcript = inbound.text
            return [
                OutboundMessage(
                    kind="text",
                    text_hi=f"सुना गया: {inbound.text}",
                    speaker="coach",
                )
            ]

    set_session_service_factory(lambda s: AudioEchoService())
    client_msg_id = str(uuid.uuid4())
    dummy_wav = b"RIFF" + b"\x00" * 200

    async with AsyncClient(
        transport=ASGITransport(app=web_test_app), base_url="http://test"
    ) as client:
        res = await client.post(
            "/api/chat/audio",
            data={"client_msg_id": client_msg_id},
            files={"file": ("audio.wav", dummy_wav, "audio/wav")},
        )
        assert res.status_code == 202
        assert res.json()["status"] == "accepted"

        res_poll = await client.get("/api/chat/messages")
        assert res_poll.status_code == 200
        poll_data = res_poll.json()
        assert poll_data["pending"] is False
        msgs = poll_data["messages"]
        assert len(msgs) == 2
        # Inbound message was transcribed by MockSTT
        assert msgs[0]["direction"] == "in"
        assert msgs[0]["text"] is not None
        assert len(msgs[0]["text"]) > 0
        # Outbound bot message replied to transcript
        assert msgs[1]["direction"] == "out"
        assert recorded_transcript is not None


@pytest.mark.asyncio
async def test_e2e_button_press_submission(
    web_test_app: FastAPI,
) -> None:
    """Button press is submitted, processed by SessionService, and polled."""
    received_button_id: str | None = None

    class ButtonService:
        async def handle_inbound(self, inbound: InboundMessage) -> list[OutboundMessage]:
            nonlocal received_button_id
            received_button_id = inbound.button_id
            return [
                OutboundMessage(
                    kind="buttons",
                    text_hi="बटन प्राप्त हुआ। अगला कदम चुनें:",
                    buttons=[Button(id="btn_next_step", title_hi="आगे बढ़ें")],
                    speaker="abhyas",
                )
            ]

    set_session_service_factory(lambda s: ButtonService())
    client_msg_id = str(uuid.uuid4())

    async with AsyncClient(
        transport=ASGITransport(app=web_test_app), base_url="http://test"
    ) as client:
        res = await client.post(
            "/api/chat/button",
            json={"client_msg_id": client_msg_id, "button_id": "btn_ready_practice"},
        )
        assert res.status_code == 202
        assert res.json()["status"] == "accepted"
        assert received_button_id == "btn_ready_practice"

        res_poll = await client.get("/api/chat/messages")
        assert res_poll.status_code == 200
        msgs = res_poll.json()["messages"]
        assert len(msgs) == 2
        assert msgs[0]["kind"] == "button"
        assert msgs[0]["text"] == "btn_ready_practice"
        assert msgs[1]["kind"] == "buttons"
        assert msgs[1]["buttons"][0]["id"] == "btn_next_step"


@pytest.mark.asyncio
async def test_e2e_real_session_service_onboarding_turn(
    web_test_app: FastAPI,
) -> None:
    """Connects real SessionService with FakeSessionRepository end-to-end."""
    fake_repo = FakeSessionRepository()
    session_service = SessionService(repository=fake_repo)
    set_session_service_factory(lambda s: session_service)

    client_msg_id = str(uuid.uuid4())

    async with AsyncClient(
        transport=ASGITransport(app=web_test_app), base_url="http://test"
    ) as client:
        # In NEW onboarding state, teacher clicks 'btn_agree'
        res = await client.post(
            "/api/chat/button",
            json={"client_msg_id": client_msg_id, "button_id": "btn_agree"},
        )
        assert res.status_code == 202
        assert res.json()["status"] == "accepted"

        # Poll messages -> real SessionService produces ask_join_code prompt
        res_poll = await client.get("/api/chat/messages")
        assert res_poll.status_code == 200
        msgs = res_poll.json()["messages"]
        assert len(msgs) == 2
        assert msgs[0]["kind"] == "button"
        assert msgs[1]["direction"] == "out"
        # From messages_hi.yaml: ask_join_code prompt mentions code
        assert any(token in (msgs[1]["text"] or "") for token in ["कोड", "ब्लॉक", "code", "join"])


# ── Review Items 1, 3, 4, 6 Tests ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_csrf_on_api_post_routes(web_test_app: FastAPI) -> None:
    """Item 1: POST to /api without CSRF fails (403); with valid CSRF succeeds."""
    # Re-enable real verify_csrf_token for this test
    web_test_app.dependency_overrides.pop(verify_csrf_token, None)

    async with AsyncClient(
        transport=ASGITransport(app=web_test_app), base_url="http://test"
    ) as client:
        # 1. POST without CSRF cookie or header -> 403
        res_no_csrf = await client.post(
            "/api/chat/text",
            json={"client_msg_id": str(uuid.uuid4()), "text": "नमस्ते"},
        )
        assert res_no_csrf.status_code == 403

        # 2. POST with cookie but invalid header -> 403
        token = generate_csrf_token()
        client.cookies.set(CSRF_COOKIE_NAME, token)
        res_bad_header = await client.post(
            "/api/chat/text",
            headers={CSRF_HEADER_NAME: "wrong-token"},
            json={"client_msg_id": str(uuid.uuid4()), "text": "नमस्ते"},
        )
        assert res_bad_header.status_code == 403

        # 3. POST with matching CSRF cookie and x-csrf-token header -> 202
        res_valid = await client.post(
            "/api/chat/text",
            headers={CSRF_HEADER_NAME: token},
            json={"client_msg_id": str(uuid.uuid4()), "text": "नमस्ते"},
        )
        assert res_valid.status_code == 202

    # Restore override for other tests
    web_test_app.dependency_overrides[verify_csrf_token] = lambda: None


@pytest.mark.asyncio
async def test_csrf_bearer_token_bypass_rules(
    web_test_app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Item 1: Bearer-token auth allowed to bypass CSRF ONLY when settings.ENVIRONMENT != 'production'."""
    web_test_app.dependency_overrides.pop(verify_csrf_token, None)

    async with AsyncClient(
        transport=ASGITransport(app=web_test_app), base_url="http://test"
    ) as client:
        # In non-production (e.g. test), Bearer token skips CSRF
        monkeypatch.setattr(settings, "ENVIRONMENT", "test")
        res_dev = await client.post(
            "/api/chat/text",
            headers={"Authorization": "Bearer test-bearer-token"},
            json={"client_msg_id": str(uuid.uuid4()), "text": "नमस्ते"},
        )
        assert res_dev.status_code == 202

        # In production, Bearer token does NOT bypass CSRF -> 403
        monkeypatch.setattr(settings, "ENVIRONMENT", "production")
        res_prod = await client.post(
            "/api/chat/text",
            headers={"Authorization": "Bearer test-bearer-token"},
            json={"client_msg_id": str(uuid.uuid4()), "text": "नमस्ते"},
        )
        assert res_prod.status_code == 403

    web_test_app.dependency_overrides[verify_csrf_token] = lambda: None


@pytest.mark.asyncio
async def test_admin_chat_requires_explicit_demo_teacher(web_test_app: FastAPI) -> None:
    """Item 3: Admin opens chat only as an explicit demo teacher (?as=<demo_id>, is_demo=True) or 400."""
    admin_user = AppUser(
        id=uuid.uuid4(),
        username="admin",
        role="admin",
        teacher_id=None,
        display_name="व्यवस्थापक",
        password_hash="hash",
    )
    demo_teacher_id = uuid.uuid4()
    demo_teacher = Teacher(
        id=demo_teacher_id,
        name="डेमो शिक्षिका 1",
        preferred_channel="web",
        is_demo=True,
    )
    real_teacher_id = uuid.uuid4()
    real_teacher = Teacher(
        id=real_teacher_id,
        name="वास्तविक शिक्षिका",
        preferred_channel="web",
        is_demo=False,
    )

    web_test_app.dependency_overrides[get_current_user] = lambda: admin_user

    async def mock_db_with_teachers() -> AsyncSession:
        db = AsyncMock(spec=AsyncSession)

        async def get_mock(entity: Any, ident: Any) -> Any:
            if entity is Teacher:
                if ident == demo_teacher_id:
                    return demo_teacher
                if ident == real_teacher_id:
                    return real_teacher
            return None

        db.get.side_effect = get_mock
        db.commit = AsyncMock()
        mock_res = MagicMock()
        mock_res.scalar_one_or_none.return_value = None
        db.execute.return_value = mock_res
        return db

    web_test_app.dependency_overrides[get_db_session] = mock_db_with_teachers

    async with AsyncClient(
        transport=ASGITransport(app=web_test_app), base_url="http://test"
    ) as client:
        # 1. Admin without selection -> 400
        res_no_as = await client.post(
            "/api/chat/text",
            json={"client_msg_id": str(uuid.uuid4()), "text": "नमस्ते"},
        )
        assert res_no_as.status_code == 400

        # 2. Admin with non-demo teacher -> 400
        res_non_demo = await client.post(
            f"/api/chat/text?as={real_teacher_id}",
            json={"client_msg_id": str(uuid.uuid4()), "text": "नमस्ते"},
        )
        assert res_non_demo.status_code == 400

        # 3. Admin with explicit demo teacher -> 202
        res_demo = await client.post(
            f"/api/chat/text?as={demo_teacher_id}",
            json={"client_msg_id": str(uuid.uuid4()), "text": "नमस्ते"},
        )
        assert res_demo.status_code == 202


@pytest.mark.asyncio
async def test_idempotency_cross_teacher_collision_409(web_test_app: FastAPI) -> None:
    """Item 4: Lookup of idempotency key filters by teacher_id; cross-teacher collision -> 409 Conflict."""
    teacher_a_id = uuid.uuid4()
    teacher_b_id = uuid.uuid4()
    teacher_a = Teacher(id=teacher_a_id, name="शिक्षिका A", preferred_channel="web")
    teacher_b = Teacher(id=teacher_b_id, name="शिक्षिका B", preferred_channel="web")

    user_a = AppUser(
        id=uuid.uuid4(), username="t_a", role="teacher", teacher_id=teacher_a_id, password_hash="h"
    )
    user_b = AppUser(
        id=uuid.uuid4(), username="t_b", role="teacher", teacher_id=teacher_b_id, password_hash="h"
    )

    messages_store: dict[str, Message] = {}

    current_test_user = user_a
    web_test_app.dependency_overrides[get_current_user] = lambda: current_test_user

    async def mock_db_cross() -> AsyncSession:
        db = AsyncMock(spec=AsyncSession)

        async def get_mock(entity: Any, ident: Any) -> Any:
            if entity is Teacher:
                if ident == teacher_a_id:
                    return teacher_a
                if ident == teacher_b_id:
                    return teacher_b
            return None

        def add_mock(instance: Any) -> None:
            if isinstance(instance, Message):
                messages_store[instance.channel_msg_id] = instance

        async def execute_mock(stmt: Any) -> Any:
            mock_res = MagicMock()
            str_stmt = str(stmt)
            if "FROM message" in str_stmt:
                params = list(getattr(stmt.compile(), "params", {}).values())
                matched = None
                for p in params:
                    if p in messages_store:
                        matched = messages_store[p]
                        break
                mock_res.scalar_one_or_none.return_value = matched
            return mock_res

        db.get.side_effect = get_mock
        db.add.side_effect = add_mock
        db.execute.side_effect = execute_mock
        db.commit = AsyncMock()
        return db

    web_test_app.dependency_overrides[get_db_session] = mock_db_cross

    shared_client_msg_id = str(uuid.uuid4())

    async with AsyncClient(
        transport=ASGITransport(app=web_test_app), base_url="http://test"
    ) as client:
        # 1. Teacher A sends message -> 202 accepted
        res_a1 = await client.post(
            "/api/chat/text",
            json={"client_msg_id": shared_client_msg_id, "text": "संदेश A"},
        )
        assert res_a1.status_code == 202
        assert res_a1.json()["status"] == "accepted"

        # 2. Teacher A resends same message -> 202 duplicate_ignored
        res_a2 = await client.post(
            "/api/chat/text",
            json={"client_msg_id": shared_client_msg_id, "text": "संदेश A"},
        )
        assert res_a2.status_code == 202
        assert res_a2.json()["status"] == "duplicate_ignored"

        # 3. Teacher B uses same client_msg_id -> 409 Conflict
        current_test_user = user_b
        res_b = await client.post(
            "/api/chat/text",
            json={"client_msg_id": shared_client_msg_id, "text": "संदेश B"},
        )
        assert res_b.status_code == 409


@pytest.mark.asyncio
async def test_missing_audio_returns_404_in_all_environments(
    web_test_app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Missing audio returns 404 in both test and prod mode without fallback synthesis."""
    async with AsyncClient(
        transport=ASGITransport(app=web_test_app), base_url="http://test"
    ) as client:
        # In production mode: missing audio returns 404
        monkeypatch.setattr(settings, "ENVIRONMENT", "production")
        res_prod = await client.get("/api/audio/missing_audio_ref.wav")
        assert res_prod.status_code == 404
        assert "Audio file not found" in res_prod.json()["detail"]

        # In test mode: missing audio ALSO returns 404 (no MockTTS fallback)
        monkeypatch.setattr(settings, "ENVIRONMENT", "test")
        res_test = await client.get("/api/audio/missing_audio_ref.wav")
        assert res_test.status_code == 404
        assert "Audio file not found" in res_test.json()["detail"]
