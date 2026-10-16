"""Scheduler tick, fast-forward and APScheduler wiring (spec/08 §8.6, T24).

Every 60 s `run_due_jobs` claims due rows from `scheduled_job` one at a time with
`FOR UPDATE SKIP LOCKED`, so two app instances never run the same job. The row
stays locked for the whole handler run; if the process dies mid-job the
transaction rolls back and the job is simply pending again.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.app.db.models import ScheduledJob
from backend.app.jobs import schedule, tunables
from backend.app.jobs.handlers import (
    HANDLERS,
    ChannelResolver,
    ComputeAggregates,
    JobContext,
    JobHandler,
    JobSkipped,
    _payload_text,
    default_channel_resolver,
    plan_recurring_jobs,
)

if TYPE_CHECKING:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler

logger = logging.getLogger("abhyas.jobs.tick")

Clock = Callable[[], datetime]
SessionFactory = async_sessionmaker[AsyncSession]


def utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class JobOutcome:
    job_id: uuid.UUID
    kind: str
    status: str
    error: str | None = None


@dataclass(frozen=True, slots=True)
class FastForwardResult:
    advanced: int
    outcomes: list[JobOutcome]


def _default_session_factory() -> SessionFactory:
    from backend.app.db.session import async_session_factory

    return async_session_factory


async def _run_job(
    session: AsyncSession,
    job: ScheduledJob,
    *,
    now: datetime,
    handlers: Mapping[str, JobHandler],
    resolve_channel: ChannelResolver,
    compute_aggregates: ComputeAggregates | None,
) -> JobOutcome:
    """Runs one claimed job and records the result on its row. Caller commits."""
    job_id, kind = job.id, job.kind
    job.attempts += 1
    attempts = job.attempts

    handler = handlers.get(kind)
    if handler is None:
        reason = f"unknown job kind: {kind}"
        job.status = "failed"
        job.last_error = reason
        logger.error("job %s has unknown kind %s", job_id, kind)
        return JobOutcome(job_id, kind, "failed", reason)

    ctx = JobContext(
        session=session,
        now=now,
        resolve_channel=resolve_channel,
        compute_aggregates=compute_aggregates,
    )
    try:
        # Savepoint: a failing handler rolls back its own writes, not the attempts bump.
        async with session.begin_nested():
            await handler(ctx, job)
    except JobSkipped as skip:
        reason = f"skipped: {skip}"
        job.status = "cancelled"
        job.last_error = reason
        logger.info("job %s (%s) skipped: %s", job_id, kind, skip)
        return JobOutcome(job_id, kind, "cancelled", reason)
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"[:500]
        logger.exception("job %s (%s) failed on attempt %d", job_id, kind, attempts)
        # Assign absolute values and return locals: the savepoint rollback may have
        # expired `job`, and reading an expired attribute would do I/O in async code.
        status = "failed" if attempts >= tunables.SCHEDULER_MAX_ATTEMPTS else "pending"
        job.status = status
        job.last_error = error
        if status == "pending":
            job.run_at = now + schedule.retry_delay(attempts, tunables.SCHEDULER_RETRY_BASE_SECONDS)
        return JobOutcome(job_id, kind, status, error)

    job.status = "done"
    job.last_error = None
    return JobOutcome(job_id, kind, "done")


async def run_due_jobs(
    *,
    session_factory: SessionFactory | None = None,
    clock: Clock = utc_now,
    handlers: Mapping[str, JobHandler] = HANDLERS,
    resolve_channel: ChannelResolver = default_channel_resolver,
    compute_aggregates: ComputeAggregates | None = None,
    limit: int | None = None,
) -> list[JobOutcome]:
    """Claims and runs due jobs (status pending, run_at <= now), one transaction each."""
    factory = session_factory or _default_session_factory()
    max_jobs = limit if limit is not None else tunables.SCHEDULER_BATCH_LIMIT
    now = clock()
    outcomes: list[JobOutcome] = []

    while len(outcomes) < max_jobs:
        async with factory() as session:
            job = (
                await session.execute(
                    select(ScheduledJob)
                    .where(ScheduledJob.status == "pending", ScheduledJob.run_at <= now)
                    .order_by(ScheduledJob.run_at)
                    .limit(1)
                    .with_for_update(skip_locked=True)
                )
            ).scalar_one_or_none()
            if job is None:
                break
            outcomes.append(
                await _run_job(
                    session,
                    job,
                    now=now,
                    handlers=handlers,
                    resolve_channel=resolve_channel,
                    compute_aggregates=compute_aggregates,
                )
            )
            await session.commit()
    return outcomes


async def fast_forward_teacher(
    teacher_id: uuid.UUID,
    *,
    session_factory: SessionFactory | None = None,
    clock: Clock = utc_now,
    handlers: Mapping[str, JobHandler] = HANDLERS,
    resolve_channel: ChannelResolver = default_channel_resolver,
    compute_aggregates: ComputeAggregates | None = None,
) -> FastForwardResult:
    """Demo control: make a teacher's pending jobs due now, then tick immediately."""
    factory = session_factory or _default_session_factory()
    async with factory() as session:
        advanced = await session.execute(
            update(ScheduledJob)
            .where(
                ScheduledJob.status == "pending",
                _payload_text("teacher_id") == str(teacher_id),
            )
            .values(run_at=clock())
            .returning(ScheduledJob.id)
        )
        count = len(advanced.scalars().all())
        await session.commit()

    outcomes = await run_due_jobs(
        session_factory=factory,
        clock=clock,
        handlers=handlers,
        resolve_channel=resolve_channel,
        compute_aggregates=compute_aggregates,
    )
    return FastForwardResult(advanced=count, outcomes=outcomes)


async def plan_jobs(
    *, session_factory: SessionFactory | None = None, clock: Clock = utc_now
) -> int:
    """Queues the next recurring jobs (idempotent); returns how many rows were created."""
    factory = session_factory or _default_session_factory()
    async with factory() as session:
        created = await plan_recurring_jobs(session, clock())
        await session.commit()
    return len(created)


def build_scheduler(
    *, session_factory: SessionFactory | None = None, clock: Clock = utc_now
) -> AsyncIOScheduler:
    """APScheduler wiring: 60 s tick plus an hourly, idempotent recurring-job planner."""
    from apscheduler.schedulers.asyncio import AsyncIOScheduler

    scheduler = AsyncIOScheduler(timezone=UTC)

    async def _tick() -> None:
        try:
            await run_due_jobs(session_factory=session_factory, clock=clock)
        except Exception:
            logger.exception("scheduler tick failed")

    async def _plan() -> None:
        try:
            await plan_jobs(session_factory=session_factory, clock=clock)
        except Exception:
            logger.exception("recurring job planning failed")

    scheduler.add_job(
        _tick,
        "interval",
        seconds=tunables.SCHEDULER_TICK_SECONDS,
        id="job_tick",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        _plan,
        "interval",
        minutes=tunables.SCHEDULER_PLAN_MINUTES,
        id="job_plan",
        max_instances=1,
        coalesce=True,
        next_run_time=clock(),
    )
    return scheduler


def start_scheduler() -> AsyncIOScheduler | None:
    """Starts the scheduler unless disabled or running under tests. Call from app lifespan."""
    from backend.app.config import settings

    if settings.ENVIRONMENT == "test" or not tunables.SCHEDULER_ENABLED:
        logger.info("scheduler not started (environment=%s)", settings.ENVIRONMENT)
        return None
    scheduler = build_scheduler()
    scheduler.start()
    logger.info("scheduler started: tick every %ss", tunables.SCHEDULER_TICK_SECONDS)
    return scheduler
