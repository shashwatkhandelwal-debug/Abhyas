"""Tests for Weekly State Machine, Onboarding, and SessionService (spec/08 §8.1–§8.8, T20/T21)."""

import re
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.types import InboundMessage
from backend.app.db.models import (
    AdoptionEvidence,
    ConsentLog,
    ExplainScore,
    InviteCode,
    MovePath,
    Question,
    RealismRating,
    RehearsalScore,
    ReviewItem,
    SessionState,
    Teacher,
)
from backend.app.sessions.path import MovePathEntry
from backend.app.sessions.repository import SessionRepository
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


class FakeSessionRepository(SessionRepository):
    """In-memory repository fake for unit tests."""

    def __init__(self, session: AsyncSession | None = None) -> None:
        self.session = cast(AsyncSession, session)
        self._teachers: dict[UUID, Teacher] = {}
        self._session_states: dict[tuple[UUID, date], SessionState] = {}
        self._evidence: list[AdoptionEvidence] = []
        self._review_items: list[ReviewItem] = []
        self._explain_scores: list[ExplainScore] = []
        self._rehearsal_scores: list[RehearsalScore] = []
        self._consent_logs: list[ConsentLog] = []
        self._questions: list[Question] = []
        self._move_paths: list[MovePath] = []
        self._realism_ratings: list[RealismRating] = []
        self._invite_codes: dict[str, InviteCode] = {
            "KNP-C01-B1": InviteCode(
                code="KNP-C01-B1",
                cluster_id="KNP-C01",
                batch_id="KNP-B1",
                district="Kanpur Nagar",
                active=True,
            ),
            "KNP-C01-B2": InviteCode(
                code="KNP-C01-B2",
                cluster_id="KNP-C01",
                batch_id="KNP-B2",
                district="Kanpur Nagar",
                active=True,
            ),
            "DEMO": InviteCode(
                code="DEMO",
                cluster_id="DEMO-C01",
                batch_id="DEMO-B1",
                district="Kanpur Nagar",
                active=True,
            ),
        }

    async def get_or_create_teacher(self, teacher_id: UUID) -> Teacher:
        if teacher_id not in self._teachers:
            self._teachers[teacher_id] = Teacher(
                id=teacher_id,
                onboarding_state="NEW",
                address_form="f",
                preferred_channel="whatsapp",
                lite_mode=False,
                consent_service=False,
                consent_share_scores=False,
                created_at=datetime.now(UTC),
            )
        return self._teachers[teacher_id]

    async def save_teacher(self, teacher: Teacher) -> None:
        self._teachers[teacher.id] = teacher

    async def get_or_create_session_state(
        self, teacher_id: UUID, week_start: date, move_id: str
    ) -> SessionState:
        key = (teacher_id, week_start)
        if key not in self._session_states:
            self._session_states[key] = SessionState(
                teacher_id=teacher_id,
                week_start=week_start,
                move_id=move_id,
                state="LEARN",
                prior_state=None,
                rehearse_attempts=0,
                context={},
                updated_at=datetime.now(UTC),
            )
        return self._session_states[key]

    async def save_session_state(self, session_state: SessionState) -> None:
        key = (session_state.teacher_id, session_state.week_start)
        session_state.updated_at = datetime.now(UTC)
        self._session_states[key] = session_state

    async def get_invite_code(self, code: str) -> InviteCode | None:
        norm = code.strip().upper()
        return self._invite_codes.get(norm)

    async def log_consent(
        self, teacher_id: UUID, field: str, value: bool, channel: str = "whatsapp"
    ) -> ConsentLog:
        entry = ConsentLog(
            id=uuid4(),
            teacher_id=teacher_id,
            field=field,
            value=value,
            channel=channel,
            created_at=datetime.now(UTC),
        )
        self._consent_logs.append(entry)
        return entry

    async def record_adoption_evidence(
        self,
        teacher_id: UUID,
        move_id: str,
        level: int,
        source: str,
        detail: dict[str, Any] | None = None,
    ) -> AdoptionEvidence:
        ev = AdoptionEvidence(
            id=uuid4(),
            teacher_id=teacher_id,
            move_id=move_id,
            level=level,
            source=source,
            detail=detail or {},
            created_at=datetime.now(UTC),
        )
        self._evidence.append(ev)
        return ev

    async def get_adoption_evidence(self, teacher_id: UUID) -> list[AdoptionEvidence]:
        return [e for e in self._evidence if e.teacher_id == teacher_id]

    async def record_review_item(
        self, kind: str, ref_id: str, reason: str | None = None
    ) -> ReviewItem:
        item = ReviewItem(
            id=uuid4(),
            kind=kind,
            ref_id=ref_id,
            reason=reason,
            status="open",
            created_at=datetime.now(UTC),
        )
        self._review_items.append(item)
        return item

    async def record_explain_score(
        self,
        teacher_id: UUID,
        move_id: str,
        transcript: str,
        points: dict[str, Any],
        misconceptions: list[str] | None,
        confidence: float,
        needs_review: bool,
    ) -> ExplainScore:
        score = ExplainScore(
            id=uuid4(),
            teacher_id=teacher_id,
            move_id=move_id,
            transcript=transcript,
            points=points,
            misconceptions=misconceptions or [],
            confidence=confidence,
            needs_review=needs_review,
            created_at=datetime.now(UTC),
        )
        self._explain_scores.append(score)
        return score

    async def record_rehearsal_score(
        self,
        teacher_id: UUID,
        scene_id: UUID | None,
        move_id: str,
        attempt: int,
        scores: dict[str, Any],
        evidence: dict[str, Any],
        strength_hi: str,
        change_hi: str,
        exact_words_hi: str,
        confidence: float,
        needs_review: bool,
    ) -> RehearsalScore:
        score = RehearsalScore(
            id=uuid4(),
            teacher_id=teacher_id,
            scene_id=scene_id,
            move_id=move_id,
            attempt=attempt,
            scores=scores,
            evidence=evidence,
            strength_hi=strength_hi,
            change_hi=change_hi,
            exact_words_hi=exact_words_hi,
            confidence=confidence,
            needs_review=needs_review,
            created_at=datetime.now(UTC),
        )
        self._rehearsal_scores.append(score)
        return score

    async def record_move_path(
        self, teacher_id: UUID, entries: list[MovePathEntry]
    ) -> list[MovePath]:
        paths: list[MovePath] = []
        for entry in entries:
            mp = MovePath(
                teacher_id=teacher_id,
                position=entry.position,
                move_id=entry.move_id,
                reason=entry.reason,
            )
            paths.append(mp)
            self._move_paths.append(mp)
        return paths

    async def get_move_path(self, teacher_id: UUID) -> list[MovePath]:
        return [m for m in self._move_paths if m.teacher_id == teacher_id]

    async def record_realism_rating(
        self, teacher_id: UUID, rating: int, scene_id: UUID | None = None
    ) -> RealismRating:
        rr = RealismRating(
            id=uuid4(),
            teacher_id=teacher_id,
            scene_id=scene_id,
            rating=rating,
            created_at=datetime.now(UTC),
        )
        self._realism_ratings.append(rr)
        return rr

    async def record_question(
        self,
        teacher_id: UUID,
        text: str,
        category: str,
        answer_hi: str,
        source_ids: list[str],
        confidence: float,
        status: str,
    ) -> Question:
        q = Question(
            id=uuid4(),
            teacher_id=teacher_id,
            text=text,
            category=category,
            answer_hi=answer_hi,
            source_ids=source_ids,
            confidence=confidence,
            status=status,
            created_at=datetime.now(UTC),
        )
        self._questions.append(q)
        return q

    async def purge_teacher_data(self, teacher_id: UUID) -> None:
        if teacher_id in self._teachers:
            t = self._teachers[teacher_id]
            t.name = None
            t.cluster_id = None
            t.batch_id = None
            t.district = None
            t.classes = []
            t.experience_band = None
            t.first_year = False
            t.consent_service = False
            t.consent_share_scores = False
            t.onboarding_state = "NEW"

        self._evidence = [e for e in self._evidence if e.teacher_id != teacher_id]
        self._explain_scores = [e for e in self._explain_scores if e.teacher_id != teacher_id]
        self._rehearsal_scores = [r for r in self._rehearsal_scores if r.teacher_id != teacher_id]
        self._questions = [q for q in self._questions if q.teacher_id != teacher_id]
        self._move_paths = [m for m in self._move_paths if m.teacher_id != teacher_id]
        self._consent_logs = [c for c in self._consent_logs if c.teacher_id != teacher_id]
        self._realism_ratings = [r for r in self._realism_ratings if r.teacher_id != teacher_id]
        keys_to_del = [k for k in self._session_states if k[0] == teacher_id]
        for k in keys_to_del:
            del self._session_states[k]


def make_inbound(
    teacher_id: UUID | str,
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
    service = SessionService(repository=FakeSessionRepository())
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
    ctx = await service.get_or_create_context(t_id)
    assert ctx.current_state == SessionStateEnum.EXPLAIN_BACK

    # 11. EXPLAIN_BACK -> MODEL (calls check_fidelity, records explain_score)
    out11 = await service.handle_inbound(
        make_inbound(teacher_id=t_id, text="दहाई को बंडलों से और इकाई को खुली तीलियों से समझाना चाहिए।")
    )
    assert len(out11) >= 1
    ctx = await service.get_or_create_context(t_id)
    assert ctx.current_state == SessionStateEnum.MODEL
    assert len(service.repo._explain_scores) >= 1

    # 12. MODEL -> REHEARSE_INTRO
    out12 = await service.handle_inbound(make_inbound(teacher_id=t_id, button_id="btn_listen"))
    assert any("बच्चों से" in str(m.text_hi or "") for m in out12)
    ctx = await service.get_or_create_context(t_id)
    assert ctx.current_state == SessionStateEnum.REHEARSE_INTRO

    # 13. REHEARSE_INTRO -> REHEARSE (first turn)
    out13 = await service.handle_inbound(
        make_inbound(teacher_id=t_id, text="नमस्ते बच्चों, आज हम 52-17 करेंगे।")
    )
    assert len(out13) >= 1
    ctx = await service.get_or_create_context(t_id)
    assert ctx.current_state == SessionStateEnum.REHEARSE

    # 14. REHEARSE turns 2 and 3
    await service.handle_inbound(make_inbound(teacher_id=t_id, text="रवि, पहले 52 में कितने बंडल हैं?"))
    await service.handle_inbound(
        make_inbound(teacher_id=t_id, text="शाबाश, 5 बंडल और 2 खुली तीलियाँ।")
    )
    ctx = await service.get_or_create_context(t_id)
    assert ctx.rehearsal_turns_count == 3

    # 15. Stop scene with stop keyword "बस" -> FEEDBACK (evidence level 1, calls coach_feedback)
    out15 = await service.handle_inbound(make_inbound(teacher_id=t_id, text="बस"))
    ctx = await service.get_or_create_context(t_id)
    assert ctx.current_state == SessionStateEnum.FEEDBACK
    assert any("सुझाव" in str(m.text_hi or "") or "असली" in str(m.text_hi or "") for m in out15)
    evidence_rows = await service.repo.get_adoption_evidence(t_id)
    assert any(e.level == 1 for e in evidence_rows)

    # 16. FEEDBACK -> TRY_IN_CLASS
    out16 = await service.handle_inbound(make_inbound(teacher_id=t_id, button_id="btn_continue"))
    assert any("कक्षा में" in str(m.text_hi or "") for m in out16)
    ctx = await service.get_or_create_context(t_id)
    assert ctx.current_state == SessionStateEnum.TRY_IN_CLASS

    # 17. TRY_IN_CLASS -> REFLECT_SELF
    out17 = await service.handle_inbound(make_inbound(teacher_id=t_id, button_id="btn_self"))
    assert any("सवाल" in str(m.text_hi or "") for m in out17)
    ctx = await service.get_or_create_context(t_id)
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
    ctx = await service.get_or_create_context(t_id)
    assert ctx.current_state == SessionStateEnum.DONE
    assert any("शाबाश" in str(m.text_hi or "") for m in out19)

    # 20. Assert evidence recorded in DB >= 2 per §8.8
    all_evidence = await service.repo.get_adoption_evidence(t_id)
    assert len(all_evidence) >= 2
    max_level = max(e.level for e in all_evidence)
    assert max_level >= 2


def test_sessions_package_hygiene_no_broad_exceptions_and_no_devanagari() -> None:
    """Verifies all .py files in backend/app/sessions/ have zero broad exceptions,
    zero '_in_memory' constructs, and zero Devanagari literals."""
    sessions_dir = Path(__file__).parents[2] / "app" / "sessions"
    assert sessions_dir.is_dir(), f"sessions directory not found at {sessions_dir}"

    py_files = list(sessions_dir.glob("*.py"))
    assert len(py_files) >= 5, (
        f"Expected at least 5 .py files in {sessions_dir}, found {len(py_files)}"
    )

    broad_exc_pattern = re.compile(
        r"except\s+(?:\([^)]*\b(?:Exception|BaseException)\b[^)]*\)|\b(?:Exception|BaseException)\b)"
    )

    for py_file in py_files:
        content = py_file.read_text(encoding="utf-8")

        # 1. Broad exception check (bare except, except Exception/BaseException, or tuple containing them)
        assert not re.search(r"except\s*:", content), (
            f"{py_file.name} must not contain bare 'except:'. Catch specific exceptions instead."
        )
        assert not broad_exc_pattern.search(content), (
            f"{py_file.name} must not catch Exception or BaseException broadly. "
            "Catch specific exceptions instead."
        )

        # 2. No in-memory state leakage
        assert "_in_memory" not in content, (
            f"{py_file.name} must not contain forbidden substring '_in_memory'."
        )

        # 3. Hardcoded Hindi literals check (Devanagari Unicode block \u0900-\u097F)
        hindi_matches = re.findall(r"[\u0900-\u097F]+", content)
        assert not hindi_matches, (
            f"{py_file.name} must contain ZERO hardcoded Hindi literals. "
            f"Found {len(hindi_matches)} matches: {hindi_matches[:10]}"
        )


@pytest.mark.asyncio
async def test_admin_escalation_creates_review_item() -> None:
    """Verifies 'admin' query sends ask_admin, escalates, and creates review_item in DB."""
    repo = FakeSessionRepository()
    service = SessionService(repository=repo)
    t_id = uuid4()
    ctx = await service.get_or_create_context(t_id)
    ctx.onboarding_state = OnboardingStateEnum.READY
    ctx.current_state = SessionStateEnum.LEARN
    await service._sync_context_to_db(ctx, t_id)

    out = await service.handle_inbound(
        make_inbound(teacher_id=t_id, text="admin: मुझे अवकाश के बारे में पूछना है")
    )
    assert len(out) >= 1
    # Check question recorded with status='escalated'
    questions = [q for q in repo._questions if q.teacher_id == t_id]
    assert len(questions) == 1
    assert questions[0].status == "escalated"
    assert questions[0].category == "admin"

    # Check review item created for escalated question
    review_items = [
        r for r in repo._review_items if r.kind == "question" and r.ref_id == str(questions[0].id)
    ]
    assert len(review_items) == 1


@pytest.mark.asyncio
async def test_coach_skipped_when_under_three_teacher_turns() -> None:
    """Verifies scene with < 3 teacher turns skips coach, records no score, and sends scene_ended_neutral."""
    repo = FakeSessionRepository()
    service = SessionService(repository=repo)
    t_id = uuid4()
    ctx = await service.get_or_create_context(t_id)
    ctx.onboarding_state = OnboardingStateEnum.READY
    ctx.current_state = SessionStateEnum.REHEARSE_INTRO
    await service._sync_context_to_db(ctx, t_id)

    # Turn 1
    await service.handle_inbound(make_inbound(teacher_id=t_id, text="नमस्ते बच्चों"))
    # Only 1 turn, teacher sends stop word 'बस'
    out = await service.handle_inbound(make_inbound(teacher_id=t_id, text="बस"))

    # State is FEEDBACK
    ctx = await service.get_or_create_context(t_id)
    assert ctx.current_state == SessionStateEnum.FEEDBACK

    # Rehearsal scores must be EMPTY (no score recorded)
    scores = [s for s in repo._rehearsal_scores if s.teacher_id == t_id]
    assert len(scores) == 0

    # Output contains scene_ended_neutral
    assert any("फीडबैक देखते हैं" in str(m.text_hi or "") for m in out)


@pytest.mark.asyncio
async def test_feedback_realism_rating_and_unclear_handling() -> None:
    """Verifies realism rating 1-5 is persisted in RealismRating, and other text sends unclear."""
    repo = FakeSessionRepository()
    service = SessionService(repository=repo)
    t_id = uuid4()
    ctx = await service.get_or_create_context(t_id)
    ctx.onboarding_state = OnboardingStateEnum.READY
    ctx.current_state = SessionStateEnum.FEEDBACK
    await service._sync_context_to_db(ctx, t_id)

    # Send invalid text -> unclear + buttons, never empty
    out_unclear = await service.handle_inbound(make_inbound(teacher_id=t_id, text="कुछ और बात"))
    assert len(out_unclear) == 1
    assert any(b.id == "btn_continue" for b in (out_unclear[0].buttons or []))

    # Send realism rating 4
    out_rating = await service.handle_inbound(make_inbound(teacher_id=t_id, text="4"))
    assert len(out_rating) == 1
    ratings = [r for r in repo._realism_ratings if r.teacher_id == t_id]
    assert len(ratings) == 1
    assert ratings[0].rating == 4


@pytest.mark.asyncio
async def test_second_session_service_instance_continues_mid_scene_from_db() -> None:
    """Verifies a fresh SessionService instance resumes and continues a session mid-scene
    from state. Note: Uses FakeSessionRepository in-memory to prove SessionService holds
    no instance state between requests; real database continuity is tested in integration tests."""
    repo = FakeSessionRepository()
    service1 = SessionService(repository=repo)
    t_id = uuid4()

    # Advance context in service1 to REHEARSE state with 1 turn completed
    ctx1 = await service1.get_or_create_context(t_id)
    ctx1.onboarding_state = OnboardingStateEnum.READY
    ctx1.current_state = SessionStateEnum.REHEARSE
    ctx1.rehearsal_turns_count = 1
    ctx1.child_states = {"ravi": 1}
    await service1._sync_context_to_db(ctx1, t_id)

    # Simulate fresh process: new SessionService instance sharing only the DB repository
    service2 = SessionService(repository=repo)
    ctx2 = await service2.get_or_create_context(t_id)

    # Context was loaded accurately from DB alone
    assert ctx2.current_state == SessionStateEnum.REHEARSE
    assert ctx2.rehearsal_turns_count == 1
    assert ctx2.child_states == {"ravi": 1}

    # Process turn 2 in service2
    out = await service2.handle_inbound(
        make_inbound(teacher_id=t_id, text="रवि, 52 में से 10 निकालने पर कितने बचे?")
    )
    assert len(out) >= 1

    # Verify updated state persisted in DB
    ctx2_updated = await service2.get_or_create_context(t_id)
    assert ctx2_updated.current_state == SessionStateEnum.REHEARSE
    assert ctx2_updated.rehearsal_turns_count == 2
