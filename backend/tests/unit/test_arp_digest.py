"""Unit tests for ARP Digest router, role guards, CSRF, and template rendering (spec/09 §9.3, T32)."""

import unicodedata
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.auth.csrf import generate_csrf_token
from backend.app.auth.guards import get_current_user
from backend.app.core.messages import get_message
from backend.app.db.models import AppUser, Message, Question, Teacher
from backend.app.db.session import get_db_session
from backend.app.web.arp import router as arp_router


@pytest.fixture
def arp_app() -> FastAPI:
    app = FastAPI()
    app.include_router(arp_router)
    return app


@pytest.fixture
def arp_user() -> AppUser:
    return AppUser(
        id=uuid.uuid4(),
        username="arp.demo",
        role="arp",
        cluster_id="KNP-C01",
        display_name="ए.आर.पी. कल्याणपुर",
        password_hash="hash",
    )


@pytest.fixture
def teacher_user() -> AppUser:
    return AppUser(
        id=uuid.uuid4(),
        username="teacher.demo1",
        role="teacher",
        teacher_id=uuid.uuid4(),
        password_hash="hash",
    )


@pytest.mark.asyncio
async def test_arp_route_requires_arp_or_admin_role(
    arp_app: FastAPI,
    teacher_user: AppUser,
) -> None:
    """A user with role 'teacher' must be rejected with 403 Forbidden on /arp."""
    arp_app.dependency_overrides[get_current_user] = lambda: teacher_user
    arp_app.dependency_overrides[get_db_session] = lambda: AsyncMock(spec=AsyncSession)

    transport = ASGITransport(app=arp_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        res = await client.get("/arp")
        assert res.status_code == 403
        assert "Role required" in res.json()["detail"]


@pytest.mark.asyncio
async def test_arp_dashboard_renders_clean_nfc_html(
    arp_app: FastAPI,
    arp_user: AppUser,
) -> None:
    """Verifies that /arp renders template properly and content is NFC-normalized."""
    mock_db = AsyncMock(spec=AsyncSession)
    arp_app.dependency_overrides[get_current_user] = lambda: arp_user
    arp_app.dependency_overrides[get_db_session] = lambda: mock_db

    # Mock DB query results for build_arp_digest
    cluster_mock = MagicMock()
    cluster_mock.name = "कल्याणपुर क्लस्टर 1"
    mock_db.get.return_value = cluster_mock

    # Scalars mock returning 1 consenting teacher and 1 non-consenting
    t_consent = Teacher(
        id=uuid.uuid4(),
        name="सुनीता शर्मा",
        school_id="प्रा.वि. कल्यानपुर",
        cluster_id="KNP-C01",
        consent_share_scores=True,
    )
    t_non_consent = Teacher(
        id=uuid.uuid4(),
        name="गुप्त शिक्षिका",
        school_id="प्रा.वि. गुप्त",
        cluster_id="KNP-C01",
        consent_share_scores=False,
    )

    # Mock execute/scalars
    teachers_scalars = MagicMock()
    teachers_scalars.all.return_value = [t_consent, t_non_consent]

    empty_scalars = MagicMock()
    empty_scalars.all.return_value = []

    empty_exec = MagicMock()
    empty_exec.all.return_value = []

    mock_db.scalars.side_effect = [
        teachers_scalars,  # teachers query
        empty_scalars,  # session states query
        empty_scalars,  # rehearsal scores query
        empty_scalars,  # questions query
    ]
    mock_db.execute.side_effect = [
        empty_exec,  # evidence query
    ]

    transport = ASGITransport(app=arp_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        res = await client.get("/arp")
        assert res.status_code == 200
        html = res.text

        # Verify NFC normalization
        assert html == unicodedata.normalize("NFC", html)

        # Consenting teacher visible
        assert "सुनीता शर्मा" in html
        # Non-consenting teacher name NEVER visible
        assert "गुप्त शिक्षिका" not in html
        # Aggregate row visible
        assert "स्कोर साझा नहीं" in html


@pytest.mark.asyncio
async def test_arp_post_without_csrf_fails_forbidden(
    arp_app: FastAPI,
    arp_user: AppUser,
) -> None:
    """POST /arp/observation and /arp/answer without CSRF token must return 403 Forbidden."""
    arp_app.dependency_overrides[get_current_user] = lambda: arp_user
    arp_app.dependency_overrides[get_db_session] = lambda: AsyncMock(spec=AsyncSession)

    transport = ASGITransport(app=arp_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # Observation without CSRF
        res1 = await client.post(
            "/arp/observation",
            data={"teacher_id": str(uuid.uuid4()), "move_id": "TEST_MOVE"},
        )
        assert res1.status_code == 403

        # Answer without CSRF
        res2 = await client.post(
            "/arp/answer",
            data={"question_id": str(uuid.uuid4()), "answer_hi": "उत्तर"},
        )
        assert res2.status_code == 403


@pytest.mark.asyncio
async def test_arp_dashboard_csrf_cookie_reused_on_sequential_gets(
    arp_app: FastAPI,
    arp_user: AppUser,
) -> None:
    """Sequential GETs to /arp must reuse the existing CSRF token and not overwrite it."""
    mock_db = AsyncMock(spec=AsyncSession)
    arp_app.dependency_overrides[get_current_user] = lambda: arp_user
    arp_app.dependency_overrides[get_db_session] = lambda: mock_db

    cluster_mock = MagicMock()
    cluster_mock.name = "कल्याणपुर क्लस्टर 1"
    mock_db.get.return_value = cluster_mock

    empty_scalars = MagicMock()
    empty_scalars.all.return_value = []
    empty_exec = MagicMock()
    empty_exec.all.return_value = []

    # Two requests need query results
    mock_db.scalars.side_effect = [
        empty_scalars,
        empty_scalars,
        empty_scalars,
        empty_scalars,
        empty_scalars,
        empty_scalars,
        empty_scalars,
        empty_scalars,
    ]
    mock_db.execute.side_effect = [
        empty_exec,
        empty_exec,
    ]

    transport = ASGITransport(app=arp_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # First GET: establishes CSRF cookie
        res1 = await client.get("/arp")
        assert res1.status_code == 200
        first_cookie = client.cookies.get("abhyas_csrf")
        assert first_cookie is not None

        # Second GET with existing cookie present
        res2 = await client.get("/arp")
        assert res2.status_code == 200
        # Cookie should not have been overwritten with a new value
        assert client.cookies.get("abhyas_csrf") == first_cookie
        # Second response should NOT have a Set-Cookie header for abhyas_csrf
        set_cookie_header = res2.headers.get("set-cookie", "")
        assert "abhyas_csrf" not in set_cookie_header


@pytest.mark.asyncio
async def test_arp_post_answer_rejects_non_escalated_question(
    arp_app: FastAPI,
    arp_user: AppUser,
) -> None:
    """post_arp_answer must require question.status == 'escalated'; otherwise return 409 and add no message."""
    mock_db = AsyncMock(spec=AsyncSession)
    arp_app.dependency_overrides[get_current_user] = lambda: arp_user
    arp_app.dependency_overrides[get_db_session] = lambda: mock_db

    t_id = uuid.uuid4()
    q_id = uuid.uuid4()
    teacher = Teacher(
        id=t_id,
        name="रीता देवी",
        cluster_id=arp_user.cluster_id,
        consent_share_scores=True,
    )
    already_answered_q = Question(
        id=q_id,
        teacher_id=t_id,
        text="रवि को इकाई और दहाई में भ्रम है",
        status="arp_answered",  # Not "escalated"
    )

    mock_db.get.side_effect = lambda model, obj_id: (
        already_answered_q if model is Question else (teacher if model is Teacher else None)
    )

    csrf_token = generate_csrf_token()
    transport = ASGITransport(app=arp_app)
    async with AsyncClient(
        transport=transport,
        base_url="http://testserver",
        cookies={"abhyas_csrf": csrf_token},
    ) as client:
        res = await client.post(
            "/arp/answer",
            data={
                "csrf_token": csrf_token,
                "question_id": str(q_id),
                "answer_hi": "पुनः उत्तर देने का प्रयास",
            },
        )
        assert res.status_code == 409
        assert "expected 'escalated'" in res.json()["detail"]
        # Verify no message was added
        assert mock_db.add.call_count == 0


@pytest.mark.asyncio
async def test_arp_post_answer_success_uses_catalog_header(
    arp_app: FastAPI,
    arp_user: AppUser,
) -> None:
    """post_arp_answer formats outbound message using get_message('ui_arp_answer_header')."""
    mock_db = AsyncMock(spec=AsyncSession)
    arp_app.dependency_overrides[get_current_user] = lambda: arp_user
    arp_app.dependency_overrides[get_db_session] = lambda: mock_db

    t_id = uuid.uuid4()
    q_id = uuid.uuid4()
    teacher = Teacher(
        id=t_id,
        name="रीता देवी",
        cluster_id=arp_user.cluster_id,
        consent_share_scores=True,
        preferred_channel="web",
    )
    escalated_q = Question(
        id=q_id,
        teacher_id=t_id,
        text="रवि को इकाई और दहाई में भ्रम है",
        status="escalated",
    )

    mock_db.get.side_effect = lambda model, obj_id: (
        escalated_q if model is Question else (teacher if model is Teacher else None)
    )

    scalars_mock = MagicMock()
    scalars_mock.first.return_value = None
    mock_db.scalars.return_value = scalars_mock

    csrf_token = generate_csrf_token()
    transport = ASGITransport(app=arp_app)
    async with AsyncClient(
        transport=transport,
        base_url="http://testserver",
        cookies={"abhyas_csrf": csrf_token},
    ) as client:
        res = await client.post(
            "/arp/answer",
            data={
                "csrf_token": csrf_token,
                "question_id": str(q_id),
                "answer_hi": "पहले 10-10 के बंडल बनवाएँ।",
            },
            follow_redirects=False,
        )
        assert res.status_code == 303
        assert "/arp?saved=1&msg=ans" in res.headers["location"]

        # Check the Message added
        added_objects = [call.args[0] for call in mock_db.add.call_args_list]
        messages = [obj for obj in added_objects if isinstance(obj, Message)]
        assert len(messages) == 1
        expected_header = get_message("ui_arp_answer_header")
        assert messages[0].text is not None
        assert messages[0].text.startswith(expected_header)
        assert "पहले 10-10 के बंडल बनवाएँ।" in messages[0].text


@pytest.mark.asyncio
async def test_arp_post_answer_dispatches_via_whatsapp_for_whatsapp_teacher(
    arp_app: FastAPI,
    arp_user: AppUser,
) -> None:
    """post_arp_answer routes through WhatsAppChannel.send when teacher.preferred_channel == 'whatsapp'."""
    from unittest.mock import patch

    mock_db = AsyncMock(spec=AsyncSession)
    arp_app.dependency_overrides[get_current_user] = lambda: arp_user
    arp_app.dependency_overrides[get_db_session] = lambda: mock_db

    t_id = uuid.uuid4()
    q_id = uuid.uuid4()
    teacher = Teacher(
        id=t_id,
        name="सुनीता देवी",
        cluster_id=arp_user.cluster_id,
        consent_share_scores=True,
        preferred_channel="whatsapp",
        last_inbound_at=datetime.now(UTC),
    )
    escalated_q = Question(
        id=q_id,
        teacher_id=t_id,
        text="बच्चों को जोड़ में हासिल का संप्रत्यय कैसे समझाएँ?",
        status="escalated",
    )

    mock_db.get.side_effect = lambda model, obj_id: (
        escalated_q if model is Question else (teacher if model is Teacher else None)
    )

    scalars_mock = MagicMock()
    scalars_mock.first.return_value = None
    mock_db.scalars.return_value = scalars_mock

    csrf_token = generate_csrf_token()
    transport = ASGITransport(app=arp_app)

    with patch(
        "backend.app.channels.whatsapp.channel.WhatsAppChannel.send",
        new_callable=AsyncMock,
    ) as mock_wa_send:
        async with AsyncClient(
            transport=transport,
            base_url="http://testserver",
            cookies={"abhyas_csrf": csrf_token},
        ) as client:
            res = await client.post(
                "/arp/answer",
                data={
                    "csrf_token": csrf_token,
                    "question_id": str(q_id),
                    "answer_hi": "तीलियों और रबर बैंड से बंडल बनाकर समझाएँ।",
                },
                follow_redirects=False,
            )
            assert res.status_code == 303
            assert "/arp?saved=1&msg=ans" in res.headers["location"]
            mock_wa_send.assert_called_once()
            call_teacher = mock_wa_send.call_args[0][0]
            call_outbounds = mock_wa_send.call_args[0][1]
            assert call_teacher.id == t_id
            assert len(call_outbounds) == 1
            assert call_outbounds[0].template_name == "abhyas_arp_answer"
            assert call_outbounds[0].speaker == "arp"
            assert "तीलियों और रबर बैंड" in call_outbounds[0].text_hi


@pytest.mark.asyncio
async def test_arp_post_answer_whatsapp_failure_does_not_persist_undelivered_message(
    arp_app: FastAPI,
    arp_user: AppUser,
) -> None:
    """If WhatsApp dispatch raises an exception, error is logged and no Message row is persisted (Rule C)."""
    from unittest.mock import patch

    mock_db = AsyncMock(spec=AsyncSession)
    arp_app.dependency_overrides[get_current_user] = lambda: arp_user
    arp_app.dependency_overrides[get_db_session] = lambda: mock_db

    t_id = uuid.uuid4()
    q_id = uuid.uuid4()
    teacher = Teacher(
        id=t_id,
        name="सुनीता देवी",
        cluster_id=arp_user.cluster_id,
        consent_share_scores=True,
        preferred_channel="whatsapp",
    )
    escalated_q = Question(
        id=q_id,
        teacher_id=t_id,
        text="बच्चों को जोड़ में हासिल का संप्रत्यय कैसे समझाएँ?",
        status="escalated",
    )

    mock_db.get.side_effect = lambda model, obj_id: (
        escalated_q if model is Question else (teacher if model is Teacher else None)
    )

    scalars_mock = MagicMock()
    scalars_mock.first.return_value = None
    mock_db.scalars.return_value = scalars_mock

    csrf_token = generate_csrf_token()
    transport = ASGITransport(app=arp_app)

    with patch(
        "backend.app.channels.whatsapp.channel.WhatsAppChannel.send",
        side_effect=RuntimeError("Meta network failure"),
    ):
        async with AsyncClient(
            transport=transport,
            base_url="http://testserver",
            cookies={"abhyas_csrf": csrf_token},
        ) as client:
            res = await client.post(
                "/arp/answer",
                data={
                    "csrf_token": csrf_token,
                    "question_id": str(q_id),
                    "answer_hi": "तीलियों और रबर बैंड से बंडल बनाकर समझाएँ।",
                },
                follow_redirects=False,
            )
            assert res.status_code == 303
            assert "/arp?saved=1&msg=ans_wa_fail" in res.headers["location"]
            # Question is marked answered
            assert escalated_q.status == "arp_answered"
            # Exactly one Message row was added on channel "web" so teacher sees answer in app (no whatsapp row)
            added_messages = [
                call.args[0]
                for call in mock_db.add.call_args_list
                if isinstance(call.args[0], Message)
            ]
            assert len(added_messages) == 1
            assert added_messages[0].channel == "web"
            assert added_messages[0].direction == "out"


@pytest.mark.asyncio
async def test_arp_post_answer_whatsapp_success_single_message_no_duplicate(
    arp_app: FastAPI,
    arp_user: AppUser,
) -> None:
    """When WhatsApp send succeeds, exactly one Message row is persisted by wa_channel.send with no duplicates."""
    from unittest.mock import patch

    from backend.app.db.models import TeacherContact

    mock_db = AsyncMock(spec=AsyncSession)
    arp_app.dependency_overrides[get_current_user] = lambda: arp_user
    arp_app.dependency_overrides[get_db_session] = lambda: mock_db

    t_id = uuid.uuid4()
    q_id = uuid.uuid4()
    teacher = Teacher(
        id=t_id,
        name="सुनीता देवी",
        cluster_id=arp_user.cluster_id,
        consent_share_scores=True,
        preferred_channel="whatsapp",
    )
    escalated_q = Question(
        id=q_id,
        teacher_id=t_id,
        text="बच्चों को जोड़ में हासिल का संप्रत्यय कैसे समझाएँ?",
        status="escalated",
    )

    mock_db.get.side_effect = lambda model, obj_id: (
        escalated_q if model is Question else (teacher if model is Teacher else None)
    )

    scalars_mock = MagicMock()
    scalars_mock.first.return_value = None
    mock_db.scalars.return_value = scalars_mock

    contact = TeacherContact(
        teacher_id=t_id,
        phone_enc="encrypted_token",
    )
    mock_contact_result = MagicMock()
    mock_contact_result.scalar_one_or_none.return_value = contact
    mock_db.execute.return_value = mock_contact_result

    csrf_token = generate_csrf_token()
    transport = ASGITransport(app=arp_app)

    with (
        patch(
            "backend.app.channels.whatsapp.channel.WhatsAppChannel.can_send_freeform",
            return_value=True,
        ),
        patch(
            "backend.app.channels.whatsapp.channel.decrypt_phone_number",
            return_value="+919876543210",
        ),
        patch(
            "backend.app.channels.whatsapp.channel.whatsapp_client.send_text",
            new_callable=AsyncMock,
        ) as mock_send_text,
    ):
        async with AsyncClient(
            transport=transport,
            base_url="http://testserver",
            cookies={"abhyas_csrf": csrf_token},
        ) as client:
            res = await client.post(
                "/arp/answer",
                data={
                    "csrf_token": csrf_token,
                    "question_id": str(q_id),
                    "answer_hi": "तीलियों और रबर बैंड से बंडल बनाकर समझाएँ।",
                },
                follow_redirects=False,
            )
            assert res.status_code == 303
            assert mock_send_text.called
            # Exactly one Message was added by wa_channel.send, not duplicated by arp.py
            added_messages = [
                call.args[0]
                for call in mock_db.add.call_args_list
                if isinstance(call.args[0], Message)
            ]
            assert len(added_messages) == 1
            assert added_messages[0].channel == "whatsapp"
            assert added_messages[0].direction == "out"


@pytest.mark.asyncio
async def test_arp_post_answer_whatsapp_outside_window_unapproved_template_skips_cleanly(
    arp_app: FastAPI,
    arp_user: AppUser,
) -> None:
    """Outside the 24h window, unapproved template abhyas_arp_answer logs and skips cleanly without exception or fake delivery."""
    from unittest.mock import patch

    from backend.app.db.models import TeacherContact

    mock_db = AsyncMock(spec=AsyncSession)
    arp_app.dependency_overrides[get_current_user] = lambda: arp_user
    arp_app.dependency_overrides[get_db_session] = lambda: mock_db

    t_id = uuid.uuid4()
    q_id = uuid.uuid4()
    teacher = Teacher(
        id=t_id,
        name="सुनीता देवी",
        cluster_id=arp_user.cluster_id,
        consent_share_scores=True,
        preferred_channel="whatsapp",
    )
    escalated_q = Question(
        id=q_id,
        teacher_id=t_id,
        text="बच्चों को जोड़ में हासिल का संप्रत्यय कैसे समझाएँ?",
        status="escalated",
    )

    mock_db.get.side_effect = lambda model, obj_id: (
        escalated_q if model is Question else (teacher if model is Teacher else None)
    )

    scalars_mock = MagicMock()
    scalars_mock.first.return_value = None
    mock_db.scalars.return_value = scalars_mock

    contact = TeacherContact(
        teacher_id=t_id,
        phone_enc="encrypted_token",
    )
    mock_contact_result = MagicMock()
    mock_contact_result.scalar_one_or_none.return_value = contact
    mock_db.execute.return_value = mock_contact_result

    csrf_token = generate_csrf_token()
    transport = ASGITransport(app=arp_app)

    # Outside 24h window, template is unapproved (abhyas_arp_answer has approved: false in content/whatsapp_templates.yaml)
    with (
        patch(
            "backend.app.channels.whatsapp.channel.WhatsAppChannel.can_send_freeform",
            return_value=False,
        ),
        patch(
            "backend.app.channels.whatsapp.channel.decrypt_phone_number",
            return_value="+919876543210",
        ),
        patch(
            "backend.app.channels.whatsapp.channel.whatsapp_client.send_template",
            new_callable=AsyncMock,
        ) as mock_send_tpl,
    ):
        async with AsyncClient(
            transport=transport,
            base_url="http://testserver",
            cookies={"abhyas_csrf": csrf_token},
        ) as client:
            res = await client.post(
                "/arp/answer",
                data={
                    "csrf_token": csrf_token,
                    "question_id": str(q_id),
                    "answer_hi": "तीलियों और रबर बैंड से बंडल बनाकर समझाएँ।",
                },
                follow_redirects=False,
            )
            assert res.status_code == 303
            assert "/arp?saved=1&msg=ans_wa_fail" in res.headers["location"]
            assert not mock_send_tpl.called
            # Exactly one Message row was added on channel "web" so teacher sees answer in app (no whatsapp row)
            added_messages = [
                call.args[0]
                for call in mock_db.add.call_args_list
                if isinstance(call.args[0], Message)
            ]
            assert len(added_messages) == 1
            assert added_messages[0].channel == "web"
            assert added_messages[0].direction == "out"
            # Question is marked answered
            assert escalated_q.status == "arp_answered"


@pytest.mark.asyncio
async def test_arp_get_dashboard_renders_wa_undelivered_flash_message(
    arp_app: FastAPI,
    arp_user: AppUser,
) -> None:
    """GET /arp?saved=1&msg=ans_wa_fail displays the catalog message for undelivered WhatsApp answers."""
    mock_db = AsyncMock(spec=AsyncSession)
    arp_app.dependency_overrides[get_current_user] = lambda: arp_user
    arp_app.dependency_overrides[get_db_session] = lambda: mock_db

    cluster_mock = MagicMock()
    cluster_mock.name = "कल्याणपुर क्लस्टर 1"
    mock_db.get.return_value = cluster_mock

    empty_scalars = MagicMock()
    empty_scalars.all.return_value = []
    empty_exec = MagicMock()
    empty_exec.all.return_value = []

    mock_db.scalars.side_effect = [
        empty_scalars,  # teachers query
        empty_scalars,  # session states query
        empty_scalars,  # rehearsal scores query
        empty_scalars,  # questions query
    ]
    mock_db.execute.side_effect = [
        empty_exec,  # evidence query
    ]

    transport = ASGITransport(app=arp_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        res = await client.get("/arp?saved=1&msg=ans_wa_fail")
        assert res.status_code == 200
        expected_msg = get_message("ui_arp_answer_saved_wa_undelivered")
        assert expected_msg in res.text
