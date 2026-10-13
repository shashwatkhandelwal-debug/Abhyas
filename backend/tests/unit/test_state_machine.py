"""Tests for Weekly State Machine, Onboarding, and Conversation Flow (spec/08 §8.1–§8.8, T20)."""

from datetime import UTC, datetime, timedelta

import pytest

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
    assert sm.advance() == SessionStateEnum.REHEARSE
    assert sm.advance() == SessionStateEnum.FEEDBACK
    assert sm.advance() == SessionStateEnum.TRY_IN_CLASS
    assert sm.advance() == SessionStateEnum.REFLECT
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
    # Check if edge belongs to Onboarding
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
        # Weekly loop or global intent
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
        elif edge.source_state == "REFLECT":
            ctx.reflection_type = "self"

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

    # Attempt 1
    res1 = wsm.transition("btn_retry")
    assert res1.new_state == "RETRY"
    assert wsm.ctx.retries_count == 1
    assert wsm.can_retry_rehearsal() is True

    # Transition to Rehearse, then stop -> FEEDBACK
    wsm.transition("start_rehearsal")
    assert wsm.ctx.current_state == SessionStateEnum.REHEARSE
    wsm.transition("stop_scene")
    assert wsm.ctx.current_state == SessionStateEnum.FEEDBACK

    # Attempt 2
    res2 = wsm.transition("btn_retry")
    assert res2.new_state == "RETRY"
    assert wsm.ctx.retries_count == 2
    assert wsm.can_retry_rehearsal() is True

    wsm.transition("start_rehearsal")
    wsm.transition("stop_scene")
    assert wsm.ctx.current_state == SessionStateEnum.FEEDBACK

    # Attempt 3
    res3 = wsm.transition("btn_retry")
    assert res3.new_state == "RETRY"
    assert wsm.ctx.retries_count == 3
    assert wsm.can_retry_rehearsal() is False

    wsm.transition("start_rehearsal")
    wsm.transition("stop_scene")
    assert wsm.ctx.current_state == SessionStateEnum.FEEDBACK

    # Attempt 4: Limit reached -> forced forward to TRY_IN_CLASS with retry_limit message
    res4 = wsm.transition("btn_retry")
    assert res4.new_state == "TRY_IN_CLASS"
    assert res4.message_keys == ["retry_limit", "try_in_class"]
    assert wsm.ctx.current_state == SessionStateEnum.TRY_IN_CLASS


def test_delete_flow_purges_and_resets_to_new() -> None:
    """Verifies delete intent purges context and next inbound starts at NEW (§8.3, §8.8)."""
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

    res = wsm.transition("delete")
    assert res.new_state == "NEW"
    assert res.message_keys == ["data_deleted"]
    assert wsm.ctx.onboarding_state == OnboardingStateEnum.NEW
    assert wsm.ctx.name is None
    assert wsm.ctx.cluster_id is None
    assert wsm.ctx.retries_count == 0

    # Next inbound enters Onboarding at NEW
    osm = OnboardingStateMachine(ctx)
    next_res = osm.transition("btn_agree")
    assert next_res.new_state == "JOIN_CODE"


def test_full_happy_path_from_new_to_done_peer_evidence_level_three() -> None:
    """Verifies full end-to-end flow from NEW to DONE with peer reflection yielding level 3 (§8.8)."""
    ctx = SessionContext(
        teacher_id="teacher_happy",
        week_start="2026-10-12",
        current_move_id="NUM_PLACE_VALUE",
    )

    # 1. Onboarding
    osm = OnboardingStateMachine(ctx)
    assert ctx.onboarding_state == OnboardingStateEnum.NEW

    r = osm.transition("btn_agree")
    assert r.new_state == "JOIN_CODE"

    r = osm.transition("KNP-C01-B1")
    assert r.new_state == "PROFILE_NAME"

    r = osm.transition("सुनीता शर्मा")
    assert r.new_state == "PROFILE_ADDRESS"

    r = osm.transition("btn_female")
    assert r.new_state == "PROFILE_EXPERIENCE"
    assert ctx.address_form == "f"

    r = osm.transition("0-1")
    assert r.new_state == "PROFILE_CLASSES"
    assert ctx.first_year is True

    r = osm.transition("कक्षा 1-2")
    assert r.new_state == "SHARE_CONSENT"

    r = osm.transition("btn_yes")
    assert r.new_state == "PLACEMENT_INTRO"

    r = osm.transition("शुरू")
    assert r.new_state == "PLACEMENT"

    # Placement turn 1
    r = osm.transition("रवि, 52 में दहाई क्या है?")
    assert r.new_state == "PLACEMENT"

    # Placement turn 2 -> READY
    r = osm.transition("बहुत अच्छे!")
    assert r.new_state == "READY"
    assert r.message_keys == ["placement_done", "ready_first_move"]

    # Start weekly loop
    r = osm.transition("start")
    assert r.new_state == "LEARN"

    # 2. Weekly Loop
    wsm = WeeklyStateMachine(ctx)
    assert ctx.current_state == SessionStateEnum.LEARN

    # LEARN -> EXPLAIN_BACK
    r = wsm.transition("btn_understood")
    assert r.new_state == "EXPLAIN_BACK"
    assert r.message_keys == ["explain_back_prompt"]

    # EXPLAIN_BACK -> MODEL
    r = wsm.transition("दहाई को बंडलों से और इकाई को खुली तीलियों से समझाना चाहिए।")
    assert r.new_state == "MODEL"
    assert r.message_keys == ["explain_back_reply", "model_offer"]

    # MODEL -> REHEARSE
    r = wsm.transition("btn_listen")
    assert r.new_state == "REHEARSE"
    assert r.message_keys == ["model_header", "rehearse_intro"]

    # Rehearsal turns (>= 3 turns for evidence level 1)
    wsm.transition("नमस्ते बच्चों, आज हम 52-17 करेंगे।")
    wsm.transition("रवि, पहले 52 में कितने बंडल हैं?")
    wsm.transition("शाबाश, 5 बंडल और 2 खुली तीलियाँ।")
    assert ctx.rehearsal_turns_count == 3

    # End scene with stop word -> FEEDBACK (evidence level 1)
    r = wsm.transition("बस")
    assert r.new_state == "FEEDBACK"
    assert ctx.evidence_level == 1

    # FEEDBACK -> TRY_IN_CLASS
    r = wsm.transition("btn_continue")
    assert r.new_state == "TRY_IN_CLASS"
    assert r.message_keys == ["try_in_class"]

    # TRY_IN_CLASS -> REFLECT (peer observation path)
    r = wsm.transition("btn_peer")
    assert r.new_state == "REFLECT"
    assert r.message_keys == ["peer_item"]
    assert ctx.reflection_type == "peer"

    # REFLECT -> DONE (evidence level 3 for peer)
    r = wsm.transition("reflection_done")
    assert r.new_state == "DONE"
    assert r.message_keys == ["week_done"]
    assert ctx.evidence_level == 3


def test_self_reflection_yields_evidence_level_two() -> None:
    """Verifies that self reflection path records evidence level 2 (§8.2, §8.8)."""
    ctx = SessionContext(
        teacher_id="t_self",
        week_start="2026-10-12",
        current_move_id="NUM_PLACE_VALUE",
        current_state=SessionStateEnum.TRY_IN_CLASS,
        evidence_level=1,
    )
    wsm = WeeklyStateMachine(ctx)

    r1 = wsm.transition("btn_self")
    assert r1.new_state == "REFLECT"
    assert r1.message_keys == ["reflect_q"]
    assert ctx.reflection_type == "self"

    r2 = wsm.transition("reflection_done")
    assert r2.new_state == "DONE"
    assert r2.message_keys == ["week_done"]
    assert ctx.evidence_level == 2
