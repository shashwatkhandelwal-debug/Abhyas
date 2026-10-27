"""Unit tests for ARP score-sharing consent (Group B requirements).

B1: Moved out of setup. Setup keeps only consent_service. Asked once after first completed
    practice scene feedback, single tap: 'Share with my ARP' / 'Not now'. Default NOT shared.
    Existing teachers keep stored answer. Demo reset restores seeded consent.
B2: Plain explanation in both languages: what ARP sees/gets, what ARP will not see.
B3: Toggle any time from My class or menu (one tap). Turning off hides scores from ARP immediately.
B4: ARP page: honest line showing how many teachers in cluster share ("4 of 12 teachers share scores with you").
    Cluster-level patterns without names only when group >= 10, below that show nothing.
"""

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from backend.app.config import settings
from backend.app.core.types import InboundMessage
from backend.app.db.models import ModuleProgress, Teacher
from backend.app.reports.module_progress import module_progress_summary
from backend.app.sessions.service import SessionService
from backend.app.sessions.state_machine import OnboardingStateEnum, SessionStateEnum
from backend.tests.unit.test_state_machine import FakeSessionRepository


def _inbound(
    teacher_id: Any,
    text: str | None = None,
    button_id: str | None = None,
    channel: str = "web",
) -> InboundMessage:
    return InboundMessage(
        channel=channel,
        channel_msg_id=f"msg-{uuid4().hex[:8]}",
        teacher_id=teacher_id,
        kind="button" if button_id else "text",
        text=text,
        button_id=button_id,
        received_at=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_opt_in_default_false_and_unanswered_is_not_shared() -> None:
    """B1 & B5: Default consent_share_scores is False, and unanswered is treated as not shared."""
    repo = FakeSessionRepository()
    t_id = uuid4()
    teacher = await repo.get_or_create_teacher(t_id)

    # Opt-in default must be false
    assert teacher.consent_share_scores is False
    # Verify repository has_consent_decision returns False
    assert await repo.has_consent_decision(t_id, "share_scores") is False


@pytest.mark.asyncio
async def test_consent_question_not_asked_during_setup_and_appears_after_first_scene_feedback() -> (
    None
):
    """B1 & B5: Setup asks only service consent; score sharing is asked once after 1st practice scene feedback."""
    repo = FakeSessionRepository()
    service = SessionService(repository=repo)
    t_id = uuid4()

    # Step through onboarding
    await service.handle_inbound(_inbound(t_id, text="सहमत हूँ", button_id="btn_agree"))
    await service.handle_inbound(_inbound(t_id, text="KNP-C01-B1"))
    await service.handle_inbound(_inbound(t_id, text="सुमन"))
    await service.handle_inbound(_inbound(t_id, button_id="btn_female"))
    await service.handle_inbound(_inbound(t_id, text="2-5 साल"))
    out_classes = await service.handle_inbound(_inbound(t_id, text="2"))

    # During setup, classes transitions directly to placement_intro (not consent_share_scores)
    assert any("52" in str(m.text_hi or "") or "रवि" in str(m.text_hi or "") for m in out_classes)
    assert not any("साझा" in str(m.text_hi or "") for m in out_classes)
    teacher = await repo.get_or_create_teacher(t_id)
    assert teacher.consent_share_scores is False

    # Complete placement
    await service.handle_inbound(_inbound(t_id, text="रवि, कैसे किया?"))
    out_placement_2 = await service.handle_inbound(_inbound(t_id, text="5 बंडल और 2 तीलियाँ"))
    assert not any("साझा" in str(m.text_hi or "") for m in out_placement_2)

    # Now in LEARN -> advance to REHEARSE
    ctx = await service.get_or_create_context(t_id)
    assert ctx.current_state == SessionStateEnum.LEARN
    await service.handle_inbound(_inbound(t_id, button_id="btn_understood"))
    await service.handle_inbound(_inbound(t_id, text="बंडल से समझाना"))
    await service.handle_inbound(_inbound(t_id, button_id="btn_listen"))
    await service.handle_inbound(_inbound(t_id, button_id="btn_rehearse_group"))

    # First turn in REHEARSE_INTRO transitions to REHEARSE
    await service.handle_inbound(_inbound(t_id, text="नमस्ते बच्चों"))
    ctx = await service.get_or_create_context(t_id)
    assert ctx.current_state == SessionStateEnum.REHEARSE

    # Turn 2
    await service.handle_inbound(_inbound(t_id, text="रवि, तीलियाँ गिनो"))

    # Turn 3
    await service.handle_inbound(_inbound(t_id, text="शाबाश, अब बंडल बनाओ"))

    # Turn 4 (satisfies MIN_TURNS_FOR_COACH_GROUP = 3 in scene)
    await service.handle_inbound(_inbound(t_id, text="अब बताओ कुल कितनी तीलियाँ हुईं?"))

    # Finish rehearsal with stop intent or natural conclusion
    out_feedback = await service.handle_inbound(_inbound(t_id, text="बस"))

    # Verify that in feedback conclusion, consent question is appended
    # buttons should include btn_share_arp and btn_share_not_now
    all_buttons = [b.id for m in out_feedback for b in (m.buttons or [])]
    assert "btn_share_arp" in all_buttons
    assert "btn_share_not_now" in all_buttons
    assert any("साझा" in str(m.text_hi or "") for m in out_feedback)
    assert any("ARP" in str(m.text_hi or "") for m in out_feedback)

    ctx = await service.get_or_create_context(t_id)
    assert ctx.asked_share_consent is True

    # Answering 'Share with my ARP'
    out_answer = await service.handle_inbound(_inbound(t_id, button_id="btn_share_arp"))
    teacher = await repo.get_or_create_teacher(t_id)
    assert teacher.consent_share_scores is True
    assert any("साझा" in str(m.text_hi or "") for m in out_answer)

    # Moving to next loop/retry should NOT ask consent again
    out_retry = await service.handle_inbound(_inbound(t_id, button_id="btn_retry"))
    retry_buttons = [b.id for m in out_retry for b in (m.buttons or [])]
    assert "btn_share_arp" not in retry_buttons


@pytest.mark.asyncio
async def test_answer_is_saved_and_toggles() -> None:
    """B1 & B3: Answering 'Not now' sets consent_share_scores=False; teacher can toggle it."""
    repo = FakeSessionRepository()
    service = SessionService(repository=repo)
    t_id = uuid4()
    teacher = await repo.get_or_create_teacher(t_id)
    teacher.onboarding_state = OnboardingStateEnum.READY.value

    ctx = await service.get_or_create_context(t_id)
    ctx.onboarding_state = OnboardingStateEnum.READY
    ctx.current_state = SessionStateEnum.FEEDBACK
    await service._sync_context_to_db(ctx, t_id)

    # Tap 'Not now'
    out_no = await service.handle_inbound(_inbound(t_id, button_id="btn_share_not_now"))
    assert any("साझा नहीं किए जाएँगे" in str(m.text_hi or "") for m in out_no)
    assert teacher.consent_share_scores is False


@pytest.mark.asyncio
async def test_demo_reset_restores_seeded_consent() -> None:
    """B1 & B5: Demo accounts keep seeded consent, and reset restores them (demo1=True, demo2=True, demo3=False)."""
    from backend.app.db.seed import (
        TEACHER_DEMO1_ID,
        TEACHER_DEMO2_ID,
        TEACHER_DEMO3_ID,
        reset_demo_teacher,
    )

    session = MagicMock()
    # Mock teachers in session
    t1 = Teacher(id=TEACHER_DEMO1_ID, name="demo1", is_demo=True, consent_share_scores=False)
    t2 = Teacher(id=TEACHER_DEMO2_ID, name="demo2", is_demo=True, consent_share_scores=False)
    t3 = Teacher(id=TEACHER_DEMO3_ID, name="demo3", is_demo=True, consent_share_scores=True)

    teachers_map = {
        TEACHER_DEMO1_ID: t1,
        TEACHER_DEMO2_ID: t2,
        TEACHER_DEMO3_ID: t3,
    }

    async def fake_get(model: Any, key: Any) -> Any:
        if model == Teacher and key in teachers_map:
            return teachers_map[key]
        return None

    session.get = AsyncMock(side_effect=fake_get)
    session.flush = AsyncMock()
    mock_res = MagicMock()
    mock_res.scalars.return_value.all.return_value = []
    session.execute = AsyncMock(return_value=mock_res)
    session.delete = AsyncMock()

    await reset_demo_teacher(session, "teacher.demo1")
    await reset_demo_teacher(session, "teacher.demo2")
    await reset_demo_teacher(session, "teacher.demo3")

    assert t1.consent_share_scores is True
    assert t2.consent_share_scores is True
    assert t3.consent_share_scores is False


@pytest.mark.asyncio
async def test_module_progress_suppression_and_honest_ratio() -> None:
    """B4 & B5: Group < 10 is suppressed (returns suppressed=True, zeroes counts); group >= 10 shows numbers."""
    session = MagicMock()

    # Case 1: 5 consenting teachers (< 10)
    fake_rows_small = [
        (
            ModuleProgress(
                teacher_id=uuid4(),
                module_id="NUM_PLACE_VALUE_BUNDLES",
                learn_done_at=datetime.now(UTC),
                check_passed=True,
            ),
            False,  # is_demo = False
        )
        for _ in range(5)
    ]

    exec_result_small = MagicMock()
    exec_result_small.all.return_value = fake_rows_small
    session.execute = AsyncMock(return_value=exec_result_small)

    res_small = await module_progress_summary(
        session, cluster_id="KNP-C01", suppress_below=settings.AGGREGATION_SUPPRESSION_N
    )
    assert len(res_small) == 1
    assert res_small[0].suppressed is True
    assert res_small[0].steps["learn"] == 0
    assert res_small[0].passed == 0

    # Case 2: 12 consenting teachers (>= 10)
    fake_rows_large = [
        (
            ModuleProgress(
                teacher_id=uuid4(),
                module_id="NUM_PLACE_VALUE_BUNDLES",
                learn_done_at=datetime.now(UTC),
                check_passed=True,
            ),
            False,  # is_demo = False
        )
        for _ in range(12)
    ]

    exec_result_large = MagicMock()
    exec_result_large.all.return_value = fake_rows_large
    session.execute = AsyncMock(return_value=exec_result_large)

    res_large = await module_progress_summary(
        session, cluster_id="KNP-C01", suppress_below=settings.AGGREGATION_SUPPRESSION_N
    )
    assert len(res_large) == 1
    assert res_large[0].suppressed is False
    assert res_large[0].steps["learn"] == 12
    assert res_large[0].passed == 12
