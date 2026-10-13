"""Tests for Weekly State Machine, Onboarding, and SessionService (spec/08 §8.1–§8.8, T20/T21)."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from backend.app.core.types import InboundMessage
from backend.app.sessions.service import SessionService
from backend.app.sessions.state_machine import (
    STATE_TRANSITION_TABLE,
    WEEKLY_LOOP_STATES,
    OnboardingStateEnum,
    OnboardingStateMachine,
    SessionContext,
    SessionStateEnum,
    TransitionEdge,
    WeeklyStateMachine,
    get_weekly_prompt_message_key,
)


def test_state_machine_happy_path_transitions() -> None:
    """Verifies sequential advance() through natural weekly loop steps (§8.2)."""
    ctx = SessionContext(
        teacher_id="t1",
        week_start="2026-10-12",
        current_move_id="NUM_BUNDLES_PLACE_VALUE",
        current_state=SessionStateEnum.LEARN,
    )
    sm = WeeklyStateMachine(ctx)

    assert sm.advance() == SessionStateEnum.EXPLAIN_BACK
    assert sm.advance() == SessionStateEnum.MODEL
    assert sm.advance() == SessionStateEnum.REHEARSE_INTRO
    assert sm.advance() == SessionStateEnum.REHEARSE
    assert sm.advance() == SessionStateEnum.FEEDBACK
    assert sm.advance() == SessionStateEnum.TRY_IN_CLASS
    assert sm.advance() == SessionStateEnum.REFLECT_SELF
    assert sm.advance() == SessionStateEnum.DONE


def test_ask_interruption_and_resume() -> None:
    """Verifies that an ASK query can interrupt any state and resumes cleanly (§8.4)."""
    ctx = SessionContext(
        teacher_id="t1",
        week_start="2026-10-12",
        current_move_id="NUM_BUNDLES_PLACE_VALUE",
        current_state=SessionStateEnum.REHEARSE,
    )
    sm = WeeklyStateMachine(ctx)

    # Teacher asks a question mid-rehearsal
    sm.handle_ask_interruption()
    assert sm.ctx.current_state == SessionStateEnum.ASK
    assert sm.ctx.prior_state_before_ask == SessionStateEnum.REHEARSE

    # Resumes prior state
    resumed_state = sm.resume_after_ask()
    assert resumed_state == SessionStateEnum.REHEARSE
    assert sm.ctx.current_state == SessionStateEnum.REHEARSE
    assert sm.ctx.prior_state_before_ask is None


def test_24_hour_window_tracking() -> None:
    """Verifies 24-hour customer service window rule (§8.6, §8.8)."""
    now = datetime.now(UTC)

    # Inbound message 2 hours ago -> within window
    ctx_recent = SessionContext(
        teacher_id="t1",
        week_start="2026-10-12",
        current_move_id="m1",
        last_inbound_at=now - timedelta(hours=2),
    )
    sm_recent = WeeklyStateMachine(ctx_recent)
    assert sm_recent.is_outside_24h_window() is False
    assert get_weekly_prompt_message_key(sm_recent.is_outside_24h_window()) == "weekly_move"

    # Inbound message 26 hours ago -> outside window (must use template)
    ctx_expired = SessionContext(
        teacher_id="t1",
        week_start="2026-10-12",
        current_move_id="m1",
        last_inbound_at=now - timedelta(hours=26),
    )
    sm_expired = WeeklyStateMachine(ctx_expired)
    assert sm_expired.is_outside_24h_window() is True
    assert get_weekly_prompt_message_key(sm_expired.is_outside_24h_window()) == "tpl_weekly_move"

    # No prior inbound -> outside window (must use template)
    ctx_none = SessionContext(
        teacher_id="t1",
        week_start="2026-10-12",
        current_move_id="m1",
        last_inbound_at=None,
    )
    sm_none = WeeklyStateMachine(ctx_none)
    assert sm_none.is_outside_24h_window() is True


def test_6_hour_inactivity_resume_rule() -> None:
    """Verifies 6-hour inactivity resume prompt detection (spec/08 §8.2)."""
    now = datetime.now(UTC)

    ctx_active = SessionContext(
        teacher_id="t1",
        week_start="2026-10-12",
        current_move_id="m1",
        current_state=SessionStateEnum.REHEARSE,
        last_inbound_at=now - timedelta(hours=2),
    )
    sm_active = WeeklyStateMachine(ctx_active)
    assert sm_active.is_inactive_resume() is False

    ctx_inactive = SessionContext(
        teacher_id="t1",
        week_start="2026-10-12",
        current_move_id="m1",
        current_state=SessionStateEnum.REHEARSE,
        last_inbound_at=now - timedelta(hours=7),
    )
    sm_inactive = WeeklyStateMachine(ctx_inactive)
    assert sm_inactive.is_inactive_resume() is True

    # Terminal state DONE does not trigger resume prompt
    ctx_done = SessionContext(
        teacher_id="t1",
        week_start="2026-10-12",
        current_move_id="m1",
        current_state=SessionStateEnum.DONE,
        last_inbound_at=now - timedelta(hours=7),
    )
    sm_done = WeeklyStateMachine(ctx_done)
    assert sm_done.is_inactive_resume() is False


@pytest.mark.parametrize(
    "edge",
    STATE_TRANSITION_TABLE,
    ids=lambda e: f"{e.source_state}_{e.input_kind}->{e.target_state}",
)
def test_table_driven_transitions_coverage(edge: TransitionEdge) -> None:
    """Exercises every (state, input-kind/intent) pair in STATE_TRANSITION_TABLE per §8.8."""
    onboarding_states = {s.value for s in OnboardingStateEnum}

    if edge.source_state in onboarding_states and edge.source_state != "LEARN":
        ctx = SessionContext(
            teacher_id="t_test",
            week_start="2026-10-12",
            current_move_id="NUM_PLACE_VALUE",
            onboarding_state=OnboardingStateEnum(edge.source_state),
        )
        if edge.source_state == "PLACEMENT" and edge.input_kind == "turn_2":
            ctx.placement_turns_count = 1

        osm = OnboardingStateMachine(ctx)
        result = osm.transition(edge.input_kind)

        assert result.new_state == edge.target_state, f"Failed on edge {edge}"
        assert tuple(result.message_keys) == edge.message_keys, f"Failed message keys on {edge}"
    else:
        ctx = SessionContext(
            teacher_id="t_test",
            week_start="2026-10-12",
            current_move_id="NUM_PLACE_VALUE",
            current_state=SessionStateEnum(edge.source_state),
        )
        if edge.source_state == "REHEARSE" and edge.input_kind == "stop_scene":
            ctx.rehearsal_turns_count = 3
        elif edge.source_state == "FEEDBACK" and edge.input_kind == "retry_limit_reached":
            ctx.retries_count = 3
        elif edge.source_state == "ASK" and edge.input_kind == "resume":
            ctx.prior_state_before_ask = SessionStateEnum.LEARN
        elif edge.source_state == "REFLECT_PEER" and edge.input_kind == "checklist_done":
            ctx.reflect_step = ctx.peer_checklist_total
        elif edge.source_state == "REFLECT_SELF" and edge.input_kind == "q2_answer":
            ctx.reflect_step = 2
        elif edge.input_kind in ("confirm_delete", "cancel_delete"):
            ctx.awaiting_delete_confirm = True
            ctx.prior_state_before_delete = SessionStateEnum.LEARN

        wsm = WeeklyStateMachine(ctx)
        result = wsm.transition(edge.input_kind)

        assert result.new_state == edge.target_state, f"Failed on edge {edge}"
        assert tuple(result.message_keys) == edge.message_keys, f"Failed message keys on {edge}"


def test_ask_from_every_weekly_state_resumes_cleanly() -> None:
    """Verifies ASK from every weekly state resumes the same state and re-sends its prompt (§8.8)."""
    for state in WEEKLY_LOOP_STATES:
        ctx = SessionContext(
            teacher_id="t1",
            week_start="2026-10-12",
            current_move_id="NUM_PLACE_VALUE",
            current_state=state,
        )
        wsm = WeeklyStateMachine(ctx)

        # 1. Ask interruption
        ask_result = wsm.transition("ask")
        assert ask_result.new_state == "ASK"
        assert ask_result.message_keys == ["ask_prompt"]
        assert wsm.ctx.current_state == SessionStateEnum.ASK
        assert wsm.ctx.prior_state_before_ask == state

        # 2. Resume after answering
        expected_prompt_key = wsm.get_state_prompt_key(state)
        resume_result = wsm.transition("teacher_resumed")
        assert resume_result.new_state == str(state)
        assert resume_result.message_keys == ["ask_resume", expected_prompt_key]
        assert wsm.ctx.current_state == state
        assert wsm.ctx.prior_state_before_ask is None


def test_free_text_does_not_silently_advance() -> None:
    """In LEARN, MODEL, TRY_IN_CLASS, DONE: free text never silently advances state (§8.3 step 4)."""
    for st in (
        SessionStateEnum.LEARN,
        SessionStateEnum.MODEL,
        SessionStateEnum.TRY_IN_CLASS,
        SessionStateEnum.DONE,
    ):
        ctx = SessionContext(
            teacher_id="t1",
            week_start="2026-10-12",
            current_move_id="NUM_PLACE_VALUE",
            current_state=st,
        )
        wsm = WeeklyStateMachine(ctx)
        res = wsm.transition("कुछ रैंडम टेक्स्ट जो बटन नहीं है")
        assert res.new_state == str(st)
        assert res.needs_intent_router is True


def test_retry_limit_enforced_at_three() -> None:
    """Verifies that rehearsal retry limit is strictly enforced at 3 (§8.2, §8.8)."""
    ctx = SessionContext(
        teacher_id="t1",
        week_start="2026-10-12",
        current_move_id="NUM_PLACE_VALUE",
        current_state=SessionStateEnum.FEEDBACK,
        retries_count=0,
    )
    wsm = WeeklyStateMachine(ctx)

    # Attempt 1 -> REHEARSE_INTRO
    res1 = wsm.transition("btn_retry")
    assert res1.new_state == "REHEARSE_INTRO"
    assert wsm.ctx.retries_count == 1
    assert wsm.can_retry_rehearsal() is True

    # Transition to Rehearse, then stop -> FEEDBACK
    wsm.transition("start_turn")
    assert wsm.ctx.current_state == SessionStateEnum.REHEARSE
    wsm.transition("stop_scene")
    assert wsm.ctx.current_state == SessionStateEnum.FEEDBACK

    # Attempt 2 -> REHEARSE_INTRO
    res2 = wsm.transition("btn_retry")
    assert res2.new_state == "REHEARSE_INTRO"
    assert wsm.ctx.retries_count == 2
    assert wsm.can_retry_rehearsal() is True

    wsm.transition("start_turn")
    wsm.transition("stop_scene")
    assert wsm.ctx.current_state == SessionStateEnum.FEEDBACK

    # Attempt 3 -> REHEARSE_INTRO
    res3 = wsm.transition("btn_retry")
    assert res3.new_state == "REHEARSE_INTRO"
    assert wsm.ctx.retries_count == 3
    assert wsm.can_retry_rehearsal() is False

    wsm.transition("start_turn")
    wsm.transition("stop_scene")
    assert wsm.ctx.current_state == SessionStateEnum.FEEDBACK

    # Attempt 4: Limit reached -> forced forward to TRY_IN_CLASS with retry_limit message
    res4 = wsm.transition("btn_retry")
    assert res4.new_state == "TRY_IN_CLASS"
    assert res4.message_keys == ["retry_limit", "try_in_class"]
    assert wsm.ctx.current_state == SessionStateEnum.TRY_IN_CLASS


def test_delete_flow_confirmation_and_purge() -> None:
    """Verifies delete flow: confirmation prompt -> confirm purges to NEW, cancel resumes (§8.3 step 7)."""
    ctx = SessionContext(
        teacher_id="t1",
        week_start="2026-10-12",
        current_move_id="NUM_PLACE_VALUE",
        current_state=SessionStateEnum.REHEARSE,
        retries_count=2,
        rehearsal_turns_count=5,
        name="सुनीता शर्मा",
        cluster_id="KNP-C01-B1",
    )
    wsm = WeeklyStateMachine(ctx)

    # 1. Delete request triggers confirmation
    res_prompt = wsm.transition("मेरा डेटा हटाएँ")
    assert res_prompt.new_state == "REHEARSE"
    assert res_prompt.message_keys == ["delete_confirm"]
    assert wsm.ctx.awaiting_delete_confirm is True

    # 2. Cancel resumes prior state
    res_cancel = wsm.transition("btn_delete_cancel")
    assert res_cancel.new_state == "REHEARSE"
    assert wsm.ctx.awaiting_delete_confirm is False

    # 3. New delete request, then confirm
    wsm.transition("delete")
    res_confirm = wsm.transition("btn_delete_confirm")
    assert res_confirm.new_state == "NEW"
    assert res_confirm.message_keys == ["data_deleted"]
    assert wsm.ctx.onboarding_state == OnboardingStateEnum.NEW
    assert wsm.ctx.name is None


def test_peer_reflection_steps_checklist_evidence_level_three() -> None:
    """Verifies REFLECT_PEER steps through checklist items and yields level 3 (§8.2, §8.8)."""
    ctx = SessionContext(
        teacher_id="t1",
        week_start="2026-10-12",
        current_move_id="NUM_PLACE_VALUE",
        current_state=SessionStateEnum.TRY_IN_CLASS,
    )
    wsm = WeeklyStateMachine(ctx)

    # Advance to REFLECT_PEER
    r = wsm.transition("btn_peer")
    assert r.new_state == "REFLECT_PEER"
    assert r.message_keys == ["peer_item"]
    assert ctx.reflect_step == 1

    # Item 1 answered -> item 2
    r2 = wsm.transition("हाँ")
    assert r2.new_state == "REFLECT_PEER"
    assert r2.message_keys == ["peer_item"]
    assert ctx.reflect_step == 2

    # Item 2 answered -> item 3
    r3 = wsm.transition("हाँ")
    assert r3.new_state == "REFLECT_PEER"
    assert r3.message_keys == ["peer_item"]
    assert ctx.reflect_step == 3

    # Item 3 answered -> DONE with evidence level 3
    r4 = wsm.transition("हाँ")
    assert r4.new_state == "DONE"
    assert r4.message_keys == ["week_done"]
    assert ctx.evidence_level == 3


def test_self_reflection_steps_q1_q2_evidence_level_two() -> None:
    """Verifies REFLECT_SELF steps Q1 then Q2, yielding evidence level 2 (§8.2, §8.8)."""
    ctx = SessionContext(
        teacher_id="t1",
        week_start="2026-10-12",
        current_move_id="NUM_PLACE_VALUE",
        current_state=SessionStateEnum.TRY_IN_CLASS,
    )
    wsm = WeeklyStateMachine(ctx)

    # Advance to REFLECT_SELF
    r = wsm.transition("btn_self")
    assert r.new_state == "REFLECT_SELF"
    assert r.message_keys == ["reflect_q"]
    assert ctx.reflect_step == 1

    # Q1 answered -> Q2
    r2 = wsm.transition("बच्चों ने तीलियाँ आसानी से गिनीं।")
    assert r2.new_state == "REFLECT_SELF"
    assert r2.message_keys == ["reflect_q"]
    assert ctx.reflect_step == 2

    # Q2 answered -> DONE with evidence level 2
    r3 = wsm.transition("अगली बार मैं बच्चों से खुद बंडल बनवाऊँगी।")
    assert r3.new_state == "DONE"
    assert r3.message_keys == ["week_done"]
    assert ctx.evidence_level == 2


def make_inbound(
    teacher_id: uuid4,
    text: str | None = None,
    button_id: str | None = None,
) -> InboundMessage:
    return InboundMessage(
        channel="whatsapp",
        channel_msg_id=f"msg-{uuid4().hex[:8]}",
        teacher_id=teacher_id,
        kind="button" if button_id else "text",
        text=text,
        button_id=button_id,
        received_at=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_full_happy_path_new_to_done_with_session_service_and_db_evidence() -> None:
    """Full happy path NEW -> DONE with SessionService asserting evidence >= 2 recorded in DB (§8.8)."""
    service = SessionService()
    t_id = uuid4()

    # 1. NEW -> JOIN_CODE (agree to consent)
    out1 = await service.handle_inbound(
        make_inbound(teacher_id=t_id, text="सहमत हूँ", button_id="btn_agree")
    )
    assert any(
        "ask_join_code" in str(m.text_hi or "") or "कोड" in str(m.text_hi or "") for m in out1
    )
    teacher = await service.repo.get_or_create_teacher(t_id)
    assert teacher.consent_service is True

    # 2. JOIN_CODE -> PROFILE_NAME (valid code)
    out2 = await service.handle_inbound(make_inbound(teacher_id=t_id, text="KNP-C01-B1"))
    assert any("ask_name" in str(m.text_hi or "") or "नाम" in str(m.text_hi or "") for m in out2)
    assert teacher.cluster_id == "KNP-C01"

    # 3. PROFILE_NAME -> PROFILE_ADDRESS
    out3 = await service.handle_inbound(make_inbound(teacher_id=t_id, text="सुनीता शर्मा"))
    assert any("संबोधित" in str(m.text_hi or "") for m in out3)
    assert teacher.name == "सुनीता शर्मा"

    # 4. PROFILE_ADDRESS -> PROFILE_EXPERIENCE
    out4 = await service.handle_inbound(
        make_inbound(teacher_id=t_id, text="शिक्षिका", button_id="btn_female")
    )
    assert any("साल" in str(m.text_hi or "") or "पढ़ा" in str(m.text_hi or "") for m in out4)
    assert teacher.address_form == "f"

    # 5. PROFILE_EXPERIENCE -> PROFILE_CLASSES
    out5 = await service.handle_inbound(make_inbound(teacher_id=t_id, text="0-1 साल"))
    assert any("कक्षा" in str(m.text_hi or "") for m in out5)
    assert teacher.first_year is True

    # 6. PROFILE_CLASSES -> SHARE_CONSENT
    out6 = await service.handle_inbound(make_inbound(teacher_id=t_id, text="कक्षा 1-2"))
    assert any("ARP" in str(m.text_hi or "") or "अंक" in str(m.text_hi or "") for m in out6)

    # 7. SHARE_CONSENT -> PLACEMENT_INTRO
    out7 = await service.handle_inbound(
        make_inbound(teacher_id=t_id, text="हाँ", button_id="btn_yes")
    )
    assert any("रवि" in str(m.text_hi or "") or "अभ्यास" in str(m.text_hi or "") for m in out7)
    assert teacher.consent_share_scores is True

    # 8. PLACEMENT_INTRO -> PLACEMENT (turn 1)
    out8 = await service.handle_inbound(
        make_inbound(teacher_id=t_id, text="रवि, 52 में से 17 घटाना है।")
    )
    assert len(out8) >= 1

    # 9. PLACEMENT turn 2 -> READY -> LEARN
    out9 = await service.handle_inbound(
        make_inbound(teacher_id=t_id, text="रवि, 52 में 5 बंडल और 2 तीलियाँ हैं।")
    )
    assert any(
        "placement_done" in str(m.text_hi or "")
        or "तैयार" in str(m.text_hi or "")
        or "तरीका" in str(m.text_hi or "")
        for m in out9
    )
    ctx = await service.get_or_create_context(t_id)
    assert ctx.onboarding_state == OnboardingStateEnum.READY
    assert ctx.current_state == SessionStateEnum.LEARN

    # 10. LEARN -> EXPLAIN_BACK
    out10 = await service.handle_inbound(make_inbound(teacher_id=t_id, button_id="btn_understood"))
    assert any("शब्दों में" in str(m.text_hi or "") for m in out10)
    assert ctx.current_state == SessionStateEnum.EXPLAIN_BACK

    # 11. EXPLAIN_BACK -> MODEL (calls check_fidelity, records explain_score)
    out11 = await service.handle_inbound(
        make_inbound(teacher_id=t_id, text="दहाई को बंडलों से और इकाई को खुली तीलियों से समझाना चाहिए।")
    )
    assert len(out11) >= 1
    assert ctx.current_state == SessionStateEnum.MODEL
    assert len(service.repo._explain_scores) >= 1

    # 12. MODEL -> REHEARSE_INTRO
    out12 = await service.handle_inbound(make_inbound(teacher_id=t_id, button_id="btn_listen"))
    assert any("बच्चों से" in str(m.text_hi or "") for m in out12)
    assert ctx.current_state == SessionStateEnum.REHEARSE_INTRO

    # 13. REHEARSE_INTRO -> REHEARSE (first turn)
    out13 = await service.handle_inbound(
        make_inbound(teacher_id=t_id, text="नमस्ते बच्चों, आज हम 52-17 करेंगे।")
    )
    assert len(out13) >= 1
    assert ctx.current_state == SessionStateEnum.REHEARSE

    # 14. REHEARSE turns 2 and 3
    await service.handle_inbound(make_inbound(teacher_id=t_id, text="रवि, पहले 52 में कितने बंडल हैं?"))
    await service.handle_inbound(
        make_inbound(teacher_id=t_id, text="शाबाश, 5 बंडल और 2 खुली तीलियाँ।")
    )
    assert ctx.rehearsal_turns_count == 3

    # 15. Stop scene with stop keyword "बस" -> FEEDBACK (evidence level 1, calls coach_feedback)
    out15 = await service.handle_inbound(make_inbound(teacher_id=t_id, text="बस"))
    assert ctx.current_state == SessionStateEnum.FEEDBACK
    assert any("सुझाव" in str(m.text_hi or "") or "असली" in str(m.text_hi or "") for m in out15)
    evidence_rows = await service.repo.get_adoption_evidence(t_id)
    assert any(e.level == 1 for e in evidence_rows)

    # 16. FEEDBACK -> TRY_IN_CLASS
    out16 = await service.handle_inbound(make_inbound(teacher_id=t_id, button_id="btn_continue"))
    assert any("कक्षा में" in str(m.text_hi or "") for m in out16)
    assert ctx.current_state == SessionStateEnum.TRY_IN_CLASS

    # 17. TRY_IN_CLASS -> REFLECT_SELF
    out17 = await service.handle_inbound(make_inbound(teacher_id=t_id, button_id="btn_self"))
    assert any("सवाल" in str(m.text_hi or "") for m in out17)
    assert ctx.current_state == SessionStateEnum.REFLECT_SELF

    # 18. Q1 answer -> Q2
    out18 = await service.handle_inbound(
        make_inbound(teacher_id=t_id, text="बच्चों ने तीलियाँ आसानी से गिनीं।")
    )
    assert any("सवाल" in str(m.text_hi or "") for m in out18)

    # 19. Q2 answer -> DONE (evidence level 2 recorded in DB)
    out19 = await service.handle_inbound(
        make_inbound(teacher_id=t_id, text="अगली बार मैं बच्चों से खुद बंडल बनवाऊँगी।")
    )
    assert ctx.current_state == SessionStateEnum.DONE
    assert any("शाबाश" in str(m.text_hi or "") for m in out19)

    # 20. Assert evidence recorded in DB >= 2 per §8.8
    all_evidence = await service.repo.get_adoption_evidence(t_id)
    assert len(all_evidence) >= 2
    max_level = max(e.level for e in all_evidence)
    assert max_level >= 2
