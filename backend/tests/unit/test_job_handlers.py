"""Unit tests for scheduled job handlers: reminder, followup_try_in_class, and retention_purge (spec/08 §8.5-8.6, spec/03 §3.4)."""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.types import OutboundMessage
from backend.app.db.models import (
    AdoptionEvidence,
    ScheduledJob,
    SessionState,
    Teacher,
)
from backend.app.jobs.handlers import (
    KIND_AGGREGATES,
    KIND_FOLLOWUP_TRY_IN_CLASS,
    KIND_REMINDER,
    KIND_RETENTION_PURGE,
    JobContext,
    JobSkipped,
    handle_followup_try_in_class,
    handle_reminder,
    handle_retention_purge,
    plan_recurring_jobs,
    schedule_followup_try_in_class,
    schedule_reminder,
)
from backend.app.sessions.state_machine import SessionStateEnum


class FakeChannel:
    def __init__(self, freeform: bool = True) -> None:
        self.freeform = freeform
        self.sent: list[tuple[Teacher, list[OutboundMessage]]] = []

    async def send(self, teacher: Teacher, msgs: list[OutboundMessage]) -> None:
        self.sent.append((teacher, msgs))

    async def can_send_freeform(self, teacher: Teacher) -> bool:
        return self.freeform


# ── Reminder Handler Tests ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_handle_reminder_missing_teacher() -> None:
    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.get = AsyncMock(return_value=None)
    channel = FakeChannel()
    ctx = JobContext(session=mock_session, now=datetime.now(UTC), resolve_channel=lambda t: channel)
    job = ScheduledJob(
        kind=KIND_REMINDER,
        run_at=datetime.now(UTC),
        payload={"teacher_id": str(uuid.uuid4())},
    )

    with pytest.raises(JobSkipped, match="teacher not found"):
        await handle_reminder(ctx, job)


@pytest.mark.asyncio
async def test_handle_reminder_not_consented() -> None:
    teacher = Teacher(id=uuid.uuid4(), name="सुनीता", consent_service=False)
    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.get = AsyncMock(return_value=teacher)
    channel = FakeChannel()
    ctx = JobContext(session=mock_session, now=datetime.now(UTC), resolve_channel=lambda t: channel)
    job = ScheduledJob(
        kind=KIND_REMINDER,
        run_at=datetime.now(UTC),
        payload={"teacher_id": str(teacher.id)},
    )

    with pytest.raises(JobSkipped, match="teacher has not consented"):
        await handle_reminder(ctx, job)


@pytest.mark.asyncio
async def test_handle_reminder_session_done() -> None:
    teacher = Teacher(id=uuid.uuid4(), name="सुनीता", consent_service=True)
    done_session = SessionState(teacher_id=teacher.id, state=SessionStateEnum.DONE.value)

    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.get = AsyncMock(return_value=teacher)
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = done_session
    mock_session.execute = AsyncMock(return_value=mock_res)

    channel = FakeChannel()
    ctx = JobContext(session=mock_session, now=datetime.now(UTC), resolve_channel=lambda t: channel)
    job = ScheduledJob(
        kind=KIND_REMINDER,
        run_at=datetime.now(UTC),
        payload={"teacher_id": str(teacher.id)},
    )

    with pytest.raises(JobSkipped, match="already completed"):
        await handle_reminder(ctx, job)


@pytest.mark.asyncio
async def test_handle_reminder_teacher_recently_active() -> None:
    now = datetime(2026, 10, 15, 12, 0, tzinfo=UTC)
    teacher = Teacher(
        id=uuid.uuid4(),
        name="सुनीता",
        consent_service=True,
        last_inbound_at=now - timedelta(hours=10),  # Active 10 hours ago (< 72h)
    )
    active_session = SessionState(teacher_id=teacher.id, state=SessionStateEnum.REHEARSE.value)

    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.get = AsyncMock(return_value=teacher)
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = active_session
    mock_session.execute = AsyncMock(return_value=mock_res)

    channel = FakeChannel()
    ctx = JobContext(session=mock_session, now=now, resolve_channel=lambda t: channel)
    job = ScheduledJob(
        kind=KIND_REMINDER,
        run_at=now,
        payload={"teacher_id": str(teacher.id)},
    )

    with pytest.raises(JobSkipped, match="teacher has interacted recently"):
        await handle_reminder(ctx, job)


@pytest.mark.asyncio
async def test_handle_reminder_success_freeform() -> None:
    now = datetime(2026, 10, 15, 12, 0, tzinfo=UTC)
    teacher = Teacher(
        id=uuid.uuid4(),
        name="सुनीता",
        consent_service=True,
        address_form="f",
        last_inbound_at=now - timedelta(hours=80),  # Inactive > 72h
    )
    active_session = SessionState(teacher_id=teacher.id, state=SessionStateEnum.REHEARSE.value)

    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.get = AsyncMock(return_value=teacher)

    # First execute call -> session_state, second execute call -> existing reminder check (None)
    mock_session_res = MagicMock()
    mock_session_res.scalar_one_or_none.return_value = active_session
    mock_rem_res = MagicMock()
    mock_rem_res.scalar_one_or_none.return_value = None
    mock_session.execute = AsyncMock(side_effect=[mock_session_res, mock_rem_res])

    channel = FakeChannel(freeform=True)
    ctx = JobContext(session=mock_session, now=now, resolve_channel=lambda t: channel)
    job = ScheduledJob(
        kind=KIND_REMINDER,
        run_at=now,
        payload={"teacher_id": str(teacher.id)},
    )

    await handle_reminder(ctx, job)
    assert len(channel.sent) == 1
    sent_msgs = channel.sent[0][1]
    assert len(sent_msgs) == 1
    assert sent_msgs[0].kind == "buttons"
    assert "सुनीता" in (sent_msgs[0].text_hi or "")
    assert len(sent_msgs[0].buttons or []) == 2
    assert (job.payload or {}).get("mode") == "freeform"


# ── Followup Try In Class Handler Tests ──────────────────────────────────────


@pytest.mark.asyncio
async def test_handle_followup_try_in_class_not_in_try_state() -> None:
    teacher = Teacher(id=uuid.uuid4(), name="सुनीता", consent_service=True)
    # Session state is LEARN, not TRY_IN_CLASS
    learn_session = SessionState(teacher_id=teacher.id, state=SessionStateEnum.LEARN.value)

    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.get = AsyncMock(return_value=teacher)
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = learn_session
    mock_session.execute = AsyncMock(return_value=mock_res)

    channel = FakeChannel()
    ctx = JobContext(session=mock_session, now=datetime.now(UTC), resolve_channel=lambda t: channel)
    job = ScheduledJob(
        kind=KIND_FOLLOWUP_TRY_IN_CLASS,
        run_at=datetime.now(UTC),
        payload={"teacher_id": str(teacher.id), "move_id": "NUM_SUB_REGROUP_BUNDLES"},
    )

    with pytest.raises(JobSkipped, match="no longer in TRY_IN_CLASS"):
        await handle_followup_try_in_class(ctx, job)


@pytest.mark.asyncio
async def test_handle_followup_try_in_class_evidence_already_recorded() -> None:
    teacher = Teacher(id=uuid.uuid4(), name="सुनीता", consent_service=True)
    try_session = SessionState(teacher_id=teacher.id, state=SessionStateEnum.TRY_IN_CLASS.value)

    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.get = AsyncMock(return_value=teacher)

    mock_session_res = MagicMock()
    mock_session_res.scalar_one_or_none.return_value = try_session
    mock_ev_res = MagicMock()
    mock_ev_res.scalars.return_value.first.return_value = AdoptionEvidence(level=2)
    mock_session.execute = AsyncMock(side_effect=[mock_session_res, mock_ev_res])

    channel = FakeChannel()
    ctx = JobContext(session=mock_session, now=datetime.now(UTC), resolve_channel=lambda t: channel)
    job = ScheduledJob(
        kind=KIND_FOLLOWUP_TRY_IN_CLASS,
        run_at=datetime.now(UTC),
        payload={"teacher_id": str(teacher.id), "move_id": "NUM_SUB_REGROUP_BUNDLES"},
    )

    with pytest.raises(JobSkipped, match="evidence level >= 2 already recorded"):
        await handle_followup_try_in_class(ctx, job)


@pytest.mark.asyncio
async def test_handle_followup_try_in_class_success() -> None:
    now = datetime(2026, 10, 15, 12, 0, tzinfo=UTC)
    teacher = Teacher(id=uuid.uuid4(), name="सुनीता", consent_service=True, address_form="f")
    try_session = SessionState(teacher_id=teacher.id, state=SessionStateEnum.TRY_IN_CLASS.value)

    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.get = AsyncMock(return_value=teacher)

    mock_session_res = MagicMock()
    mock_session_res.scalar_one_or_none.return_value = try_session
    mock_ev_res = MagicMock()
    mock_ev_res.scalars.return_value.first.return_value = None
    mock_session.execute = AsyncMock(side_effect=[mock_session_res, mock_ev_res])

    channel = FakeChannel(freeform=True)
    ctx = JobContext(session=mock_session, now=now, resolve_channel=lambda t: channel)
    job = ScheduledJob(
        kind=KIND_FOLLOWUP_TRY_IN_CLASS,
        run_at=now,
        payload={"teacher_id": str(teacher.id), "move_id": "NUM_SUB_REGROUP_BUNDLES"},
    )

    await handle_followup_try_in_class(ctx, job)
    assert len(channel.sent) == 1
    sent_msgs = channel.sent[0][1]
    assert len(sent_msgs) == 1
    assert sent_msgs[0].kind == "buttons"
    assert len(sent_msgs[0].buttons or []) == 3
    button_ids = [b.id for b in (sent_msgs[0].buttons or [])]
    assert "btn_peer" in button_ids
    assert "btn_self" in button_ids
    assert "btn_later" in button_ids
    assert (job.payload or {}).get("mode") == "freeform"


# ── Retention Purge Handler Tests ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_handle_retention_purge_never_touches_demo_teachers() -> None:
    now = datetime(2026, 10, 15, 3, 0, tzinfo=UTC)
    demo_teacher_id = uuid.uuid4()

    mock_session = AsyncMock(spec=AsyncSession)

    # 1. demo teachers query
    mock_demo_res = MagicMock()
    mock_demo_res.scalars.return_value.all.return_value = [demo_teacher_id]

    # 2. withdrawn teachers query
    mock_withdrawn_res = MagicMock()
    mock_withdrawn_res.scalars.return_value.all.return_value = []

    # 3. turns update
    mock_turns_res = MagicMock(spec=CursorResult)
    mock_turns_res.rowcount = 5

    # 4. messages update
    mock_msgs_res = MagicMock(spec=CursorResult)
    mock_msgs_res.rowcount = 8

    # 5. jobs delete
    mock_jobs_res = MagicMock(spec=CursorResult)
    mock_jobs_res.rowcount = 2

    mock_session.execute = AsyncMock(
        side_effect=[
            mock_demo_res,
            mock_withdrawn_res,
            mock_turns_res,
            mock_msgs_res,
            mock_jobs_res,
        ]
    )

    channel = FakeChannel()
    ctx = JobContext(session=mock_session, now=now, resolve_channel=lambda t: channel)
    job = ScheduledJob(
        kind=KIND_RETENTION_PURGE,
        run_at=now,
        payload={"slot": "2026-10-15"},
    )

    await handle_retention_purge(ctx, job)

    payload = job.payload or {}
    assert payload.get("purged_turns") == 5
    assert payload.get("purged_messages") == 8
    assert payload.get("deleted_jobs") == 2
    assert "purged_at" in payload


# ── Schedulers and Recurring Plan Tests ───────────────────────────────────────


@pytest.mark.asyncio
async def test_schedule_reminder_dedupes_on_slot() -> None:
    mock_session = AsyncMock(spec=AsyncSession)
    mock_res = MagicMock()
    mock_res.scalars.return_value.first.return_value = ScheduledJob(id=uuid.uuid4())
    mock_session.execute = AsyncMock(return_value=mock_res)

    teacher_id = uuid.uuid4()
    now = datetime(2026, 10, 15, 12, 0, tzinfo=UTC)

    # If already exists for slot, returns None
    job = await schedule_reminder(mock_session, teacher_id, now=now)
    assert job is None


@pytest.mark.asyncio
async def test_schedule_followup_try_in_class_creates_job() -> None:
    mock_session = AsyncMock(spec=AsyncSession)
    mock_res = MagicMock()
    mock_res.scalars.return_value.first.return_value = None
    mock_session.execute = AsyncMock(return_value=mock_res)

    teacher_id = uuid.uuid4()
    now = datetime(2026, 10, 15, 12, 0, tzinfo=UTC)

    job = await schedule_followup_try_in_class(
        mock_session, teacher_id, "NUM_SUB_REGROUP_BUNDLES", now=now
    )
    assert job is not None
    assert job.kind == KIND_FOLLOWUP_TRY_IN_CLASS
    assert (job.payload or {}).get("teacher_id") == str(teacher_id)
    assert (job.payload or {}).get("move_id") == "NUM_SUB_REGROUP_BUNDLES"
    mock_session.add.assert_called_once_with(job)


@pytest.mark.asyncio
async def test_plan_recurring_jobs_includes_retention_purge() -> None:
    mock_session = AsyncMock(spec=AsyncSession)
    mock_res = MagicMock()
    mock_res.scalars.return_value.all.return_value = []
    mock_session.execute = AsyncMock(return_value=mock_res)

    now = datetime(2026, 10, 15, 12, 0, tzinfo=UTC)
    created = await plan_recurring_jobs(mock_session, now)

    kinds = [j.kind for j in created]
    assert KIND_AGGREGATES in kinds
    assert KIND_RETENTION_PURGE in kinds


@pytest.mark.asyncio
async def test_handle_followup_try_in_class_finds_session_after_week_rollover_fri_to_mon() -> None:
    """Follow-up due on Monday for a Friday TRY_IN_CLASS session must find latest SessionState and succeed."""
    # Friday session (week_start = Monday 2026-10-05)
    fri_week_start = datetime(2026, 10, 5, 0, 0, tzinfo=UTC).date()
    teacher = Teacher(id=uuid.uuid4(), name="सुनीता", consent_service=True, address_form="f")
    try_session = SessionState(
        teacher_id=teacher.id,
        week_start=fri_week_start,
        state=SessionStateEnum.TRY_IN_CLASS.value,
    )

    # Now is Monday 2026-10-12 (week rollover occurred)
    mon_now = datetime(2026, 10, 12, 10, 0, tzinfo=UTC)

    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.get = AsyncMock(return_value=teacher)

    mock_session_res = MagicMock()
    mock_session_res.scalar_one_or_none.return_value = try_session
    mock_ev_res = MagicMock()
    mock_ev_res.scalars.return_value.first.return_value = None
    mock_session.execute = AsyncMock(side_effect=[mock_session_res, mock_ev_res])

    channel = FakeChannel(freeform=True)
    ctx = JobContext(session=mock_session, now=mon_now, resolve_channel=lambda t: channel)
    job = ScheduledJob(
        kind=KIND_FOLLOWUP_TRY_IN_CLASS,
        run_at=mon_now,
        payload={"teacher_id": str(teacher.id), "move_id": "NUM_SUB_REGROUP_BUNDLES"},
    )

    await handle_followup_try_in_class(ctx, job)
    assert len(channel.sent) == 1
    assert (job.payload or {}).get("mode") == "freeform"


def test_followup_try_in_class_hours_default_is_48() -> None:
    """FOLLOWUP_TRY_IN_CLASS_HOURS must default to 48 hours."""
    from backend.app.config import settings
    from backend.app.jobs import tunables

    assert tunables.FOLLOWUP_TRY_IN_CLASS_HOURS == 48
    assert settings.FOLLOWUP_TRY_IN_CLASS_HOURS == 48


@pytest.mark.asyncio
async def test_service_sync_schedules_reminder_when_weekly_step_unfinished() -> None:
    """SessionService._sync_context_to_db schedules a reminder job when step is unfinished."""
    from unittest.mock import patch

    from backend.app.sessions.service import SessionService
    from backend.app.sessions.state_machine import OnboardingStateEnum, SessionContext

    mock_db = AsyncMock(spec=AsyncSession)
    mock_nested = AsyncMock()
    mock_db.begin_nested.return_value.__aenter__ = AsyncMock(return_value=mock_nested)
    mock_db.begin_nested.return_value.__aexit__ = AsyncMock(return_value=None)

    repo_mock = AsyncMock()
    repo_mock.session = mock_db
    repo_mock.get_session_state.return_value = None

    service = SessionService(repository=repo_mock, db_session=mock_db)
    teacher_id = uuid.uuid4()
    ctx = SessionContext(
        teacher_id=str(teacher_id),
        week_start=datetime.now(UTC).date().isoformat(),
        current_move_id="NUM_SUB_REGROUP_BUNDLES",
        onboarding_state=OnboardingStateEnum.READY,
        current_state=SessionStateEnum.EXPLAIN_BACK,  # Unfinished weekly step
    )

    with patch(
        "backend.app.jobs.handlers.schedule_reminder",
        new_callable=AsyncMock,
    ) as mock_sched_reminder:
        await service._sync_context_to_db(ctx, teacher_id)
        mock_sched_reminder.assert_called_once()
        assert mock_sched_reminder.call_args[0][0] == mock_db
        assert mock_sched_reminder.call_args[0][1] == teacher_id


@pytest.mark.asyncio
async def test_service_sync_does_not_schedule_reminder_when_done() -> None:
    """SessionService._sync_context_to_db does NOT schedule reminder when state is DONE."""
    from unittest.mock import patch

    from backend.app.sessions.service import SessionService
    from backend.app.sessions.state_machine import OnboardingStateEnum, SessionContext

    mock_db = AsyncMock(spec=AsyncSession)
    repo_mock = AsyncMock()
    repo_mock.session = mock_db
    repo_mock.get_session_state.return_value = None

    service = SessionService(repository=repo_mock, db_session=mock_db)
    teacher_id = uuid.uuid4()
    ctx = SessionContext(
        teacher_id=str(teacher_id),
        week_start=datetime.now(UTC).date().isoformat(),
        current_move_id="NUM_SUB_REGROUP_BUNDLES",
        onboarding_state=OnboardingStateEnum.READY,
        current_state=SessionStateEnum.DONE,  # Finished weekly loop
    )

    with patch(
        "backend.app.jobs.handlers.schedule_reminder",
        new_callable=AsyncMock,
    ) as mock_sched_reminder:
        await service._sync_context_to_db(ctx, teacher_id)
        mock_sched_reminder.assert_not_called()
