"""Tests for Weekly State Machine and 24-hour window rules (§4)."""

from datetime import UTC, datetime, timedelta

from backend.app.sessions.state_machine import SessionContext, SessionStateEnum, WeeklyStateMachine


def test_state_machine_happy_path_transitions():
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


def test_ask_interruption_and_resume():
    """Verifies that an ASK query can interrupt any state and resumes cleanly."""
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


def test_24_hour_window_tracking():
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

    # Inbound message 26 hours ago -> outside window (must use template)
    ctx_expired = SessionContext(
        teacher_id="t1",
        week_start="2026-10-12",
        current_move_id="m1",
        last_inbound_at=now - timedelta(hours=26),
    )
    sm_expired = WeeklyStateMachine(ctx_expired)
    assert sm_expired.is_outside_24h_window() is True
