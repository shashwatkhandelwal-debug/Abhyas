"""Integration tests for the scheduler tick and job handlers (spec/08 §8.6, T24).

Run against real PostgreSQL (FOR UPDATE SKIP LOCKED needs it). Skipped locally when
TEST_DATABASE_URL is not set; CI provides it.
"""

import os
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from freezegun import freeze_time
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from backend.app.core.types import OutboundMessage
from backend.app.db.base import Base
from backend.app.db.models import (
    AdoptionEvidence,
    AggModuleBatch,
    AppUser,
    ARPAssignment,
    Batch,
    Cluster,
    Question,
    ScheduledJob,
    SessionState,
    Teacher,
    Turn,
)
from backend.app.jobs import tunables
from backend.app.jobs.handlers import (
    KIND_FOLLOWUP_TRY_IN_CLASS,
    KIND_REMINDER,
    KIND_RETENTION_PURGE,
    JobContext,
    latest_arp_digest_snapshot,
    plan_recurring_jobs,
    record_followup_from_button,
    schedule_followup_for_question,
)
from backend.app.jobs.tick import fast_forward_teacher, run_due_jobs

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL not set (runs in CI with real pgvector/pgvector:pg16)",
)

NOW = datetime(2026, 10, 14, 6, 0, tzinfo=UTC)  # Wednesday 11:30 IST
WEEK_START = date(2026, 10, 12)
FOLLOWUP_DELAY = timedelta(hours=tunables.FOLLOWUP_HOURS)
DUE = NOW - FOLLOWUP_DELAY  # a question answered at DUE has its follow-up due at NOW


def _async_url(url: str) -> str:
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


class FakeChannel:
    name = "fake"

    def __init__(self, freeform: bool = True) -> None:
        self.freeform = freeform
        self.sent: list[tuple[uuid.UUID, list[OutboundMessage]]] = []

    async def send(self, teacher: Teacher, msgs: list[OutboundMessage]) -> None:
        self.sent.append((teacher.id, msgs))

    async def can_send_freeform(self, teacher: Teacher) -> bool:
        return self.freeform


@pytest.fixture
async def factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    assert TEST_DATABASE_URL is not None
    engine = create_async_engine(_async_url(TEST_DATABASE_URL), poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(delete(ScheduledJob))
    maker = async_sessionmaker(engine, expire_on_commit=False)
    yield maker
    async with maker() as session:
        await session.execute(delete(ScheduledJob))
        await session.execute(delete(AggModuleBatch).where(AggModuleBatch.batch_id.like("jt-%")))
        await session.execute(delete(ARPAssignment).where(ARPAssignment.cluster_id.like("jt-%")))
        await session.execute(delete(Teacher).where(Teacher.cluster_id.like("jt-%")))
        await session.execute(delete(AppUser).where(AppUser.username.like("jt-%")))
        await session.execute(delete(Cluster).where(Cluster.id.like("jt-%")))
        await session.execute(delete(Batch).where(Batch.id.like("jt-%")))
        await session.commit()
    await engine.dispose()


async def _cluster(session: AsyncSession) -> str:
    cluster_id = f"jt-{uuid.uuid4().hex[:8]}"
    session.add(Cluster(id=cluster_id, name="जाँच संकुल"))
    await session.flush()
    return cluster_id


async def _teacher(session: AsyncSession, cluster_id: str, **kwargs: Any) -> Teacher:
    teacher = Teacher(
        id=uuid.uuid4(),
        name=kwargs.pop("name", "सुनीता"),
        cluster_id=cluster_id,
        consent_service=kwargs.pop("consent_service", True),
        **kwargs,
    )
    session.add(teacher)
    await session.flush()
    return teacher


async def _question(session: AsyncSession, teacher: Teacher, **kwargs: Any) -> Question:
    question = Question(
        id=uuid.uuid4(),
        teacher_id=teacher.id,
        text=kwargs.pop("text", "दो कक्षाएँ साथ में कैसे पढ़ाएँ और समय कैसे बाँटें"),
        status=kwargs.pop("status", "answered"),
        **kwargs,
    )
    session.add(question)
    await session.flush()
    return question


async def _job(session: AsyncSession, kind: str, run_at: datetime, **payload: Any) -> ScheduledJob:
    job = ScheduledJob(kind=kind, run_at=run_at, payload=payload or None)
    session.add(job)
    await session.flush()
    return job


async def _reload(maker: async_sessionmaker[AsyncSession], job_id: uuid.UUID) -> ScheduledJob:
    async with maker() as session:
        return (
            await session.execute(select(ScheduledJob).where(ScheduledJob.id == job_id))
        ).scalar_one()


# ── tick ─────────────────────────────────────────────────────────────────


async def test_tick_runs_only_due_pending_jobs_oldest_first(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    order: list[str] = []

    async def record(ctx: JobContext, job: ScheduledJob) -> None:
        order.append((job.payload or {})["name"])

    async with factory() as session:
        late = await _job(session, "rec", NOW - timedelta(minutes=1), name="late")
        early = await _job(session, "rec", NOW - timedelta(hours=1), name="early")
        future = await _job(session, "rec", NOW + timedelta(minutes=5), name="future")
        done = await _job(session, "rec", NOW - timedelta(hours=2), name="done")
        done.status = "done"
        await session.commit()

    outcomes = await run_due_jobs(
        session_factory=factory, clock=lambda: NOW, handlers={"rec": record}
    )

    assert order == ["early", "late"]
    assert [o.status for o in outcomes] == ["done", "done"]
    assert (await _reload(factory, early.id)).status == "done"
    assert (await _reload(factory, late.id)).attempts == 1
    assert (await _reload(factory, future.id)).status == "pending"


async def test_skip_locked_prevents_a_second_worker_from_running_a_claimed_job(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    ran: list[str] = []

    async def record(ctx: JobContext, job: ScheduledJob) -> None:
        ran.append("ran")

    async with factory() as session:
        job = await _job(session, "rec", NOW - timedelta(minutes=1))
        await session.commit()

    async with factory() as holder:
        claimed = (
            await holder.execute(
                select(ScheduledJob).where(ScheduledJob.id == job.id).with_for_update()
            )
        ).scalar_one()
        assert claimed.status == "pending"
        outcomes = await run_due_jobs(
            session_factory=factory, clock=lambda: NOW, handlers={"rec": record}
        )
        assert outcomes == []
        assert ran == []

    outcomes = await run_due_jobs(
        session_factory=factory, clock=lambda: NOW, handlers={"rec": record}
    )
    assert [o.status for o in outcomes] == ["done"]


async def test_failing_job_backs_off_then_fails_after_max_attempts(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    async def boom(ctx: JobContext, job: ScheduledJob) -> None:
        raise RuntimeError("provider down")

    async with factory() as session:
        job = await _job(session, "boom", NOW - timedelta(minutes=1))
        await session.commit()

    time_state = {"now": NOW}

    def clock() -> datetime:
        return time_state["now"]

    for attempt in range(1, tunables.SCHEDULER_MAX_ATTEMPTS + 1):
        outcomes = await run_due_jobs(session_factory=factory, clock=clock, handlers={"boom": boom})
        assert len(outcomes) == 1
        row = await _reload(factory, job.id)
        assert row.attempts == attempt
        assert row.last_error is not None and "provider down" in row.last_error
        if attempt < tunables.SCHEDULER_MAX_ATTEMPTS:
            assert row.status == "pending"
            assert row.run_at > clock()
            # not due again until the backoff has elapsed
            assert (
                await run_due_jobs(session_factory=factory, clock=clock, handlers={"boom": boom})
                == []
            )
            time_state["now"] = row.run_at
        else:
            assert row.status == "failed"


async def test_handler_writes_roll_back_when_it_fails(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    async def write_then_fail(ctx: JobContext, job: ScheduledJob) -> None:
        ctx.session.add(Batch(id=f"jt-{uuid.uuid4().hex[:6]}", name="should not persist"))
        raise RuntimeError("after write")

    async with factory() as session:
        job = await _job(session, "wf", NOW - timedelta(minutes=1))
        await session.commit()

    await run_due_jobs(session_factory=factory, clock=lambda: NOW, handlers={"wf": write_then_fail})

    async with factory() as session:
        batches = (
            (await session.execute(select(Batch).where(Batch.name == "should not persist")))
            .scalars()
            .all()
        )
    assert batches == []
    assert (await _reload(factory, job.id)).attempts == 1


async def test_unknown_kind_fails_without_retrying(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    async with factory() as session:
        job = await _job(session, "no_such_kind", NOW - timedelta(minutes=1))
        await session.commit()
    outcomes = await run_due_jobs(session_factory=factory, clock=lambda: NOW)
    assert [o.status for o in outcomes] == ["failed"]
    row = await _reload(factory, job.id)
    assert row.last_error == "unknown job kind: no_such_kind"


async def test_default_clock_works_under_freezegun(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    async def noop(ctx: JobContext, job: ScheduledJob) -> None:
        return None

    async with factory() as session:
        await _job(session, "noop", datetime(2026, 10, 14, 5, 59, tzinfo=UTC))
        await _job(session, "noop", datetime(2026, 10, 14, 6, 1, tzinfo=UTC))
        await session.commit()

    with freeze_time("2026-10-14 06:00:00", real_asyncio=True):
        outcomes = await run_due_jobs(session_factory=factory, handlers={"noop": noop})
    assert len(outcomes) == 1


# ── followup_question ────────────────────────────────────────────────────


async def test_followup_inside_window_sends_freeform_buttons(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    channel = FakeChannel(freeform=True)
    async with factory() as session:
        cluster_id = await _cluster(session)
        teacher = await _teacher(session, cluster_id)
        question = await _question(session, teacher)
        job = await schedule_followup_for_question(session, question, now=DUE)
        await session.commit()
        assert question.followup_at == NOW

    outcomes = await run_due_jobs(
        session_factory=factory, clock=lambda: NOW, resolve_channel=lambda t: channel
    )

    assert [o.status for o in outcomes] == ["done"]
    assert len(channel.sent) == 1
    teacher_id, msgs = channel.sent[0]
    assert teacher_id == teacher.id
    assert msgs[0].kind == "buttons" and msgs[0].text_hi
    assert "दो कक्षाएँ साथ में कैसे पढ़ाएँ" in msgs[0].text_hi
    assert "पढ़ाएँ और" not in msgs[0].text_hi  # topic cut at FOLLOWUP_TOPIC_MAX_WORDS
    row = await _reload(factory, job.id)
    assert (row.payload or {})["mode"] == "freeform"


async def test_followup_outside_window_sends_the_template(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    channel = FakeChannel(freeform=False)
    async with factory() as session:
        cluster_id = await _cluster(session)
        teacher = await _teacher(session, cluster_id)
        question = await _question(session, teacher)
        await schedule_followup_for_question(session, question, now=DUE)
        await session.commit()

    await run_due_jobs(
        session_factory=factory, clock=lambda: NOW, resolve_channel=lambda t: channel
    )

    msg = channel.sent[0][1][0]
    assert msg.kind == "template" and msg.template_name == "tpl_followup_question"
    assert msg.template_params[0] == "सुनीता"


@pytest.mark.parametrize(
    ("teacher_kwargs", "question_kwargs"),
    [
        ({"consent_service": False}, {}),
        ({"name": None}, {}),
        ({}, {"followup_result": "yes"}),
        ({}, {"status": "escalated"}),
    ],
    ids=["no-consent", "no-name", "already-answered", "escalated"],
)
async def test_followup_is_cancelled_when_it_no_longer_applies(
    factory: async_sessionmaker[AsyncSession],
    teacher_kwargs: dict[str, Any],
    question_kwargs: dict[str, Any],
) -> None:
    channel = FakeChannel()
    async with factory() as session:
        cluster_id = await _cluster(session)
        teacher = await _teacher(session, cluster_id, **teacher_kwargs)
        question = await _question(session, teacher, **question_kwargs)
        job = await schedule_followup_for_question(session, question, now=DUE)
        await session.commit()

    outcomes = await run_due_jobs(
        session_factory=factory, clock=lambda: NOW, resolve_channel=lambda t: channel
    )

    assert [o.status for o in outcomes] == ["cancelled"]
    assert channel.sent == []
    assert (await _reload(factory, job.id)).status == "cancelled"


async def test_followup_with_bad_payload_is_cancelled_not_retried(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    async with factory() as session:
        await _job(session, "followup_question", NOW - timedelta(minutes=1), question_id="nope")
        await session.commit()
    outcomes = await run_due_jobs(session_factory=factory, clock=lambda: NOW)
    assert [o.status for o in outcomes] == ["cancelled"]


async def test_yes_button_records_answer_and_level_2_evidence(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    async with factory() as session:
        cluster_id = await _cluster(session)
        teacher = await _teacher(session, cluster_id)
        question = await _question(session, teacher)
        await schedule_followup_for_question(
            session, question, now=DUE, move_id="NUM_PLACE_VALUE_BUNDLES"
        )
        await session.commit()

        assert await record_followup_from_button(session, teacher.id, "other", now=NOW) is False
        assert await record_followup_from_button(session, teacher.id, "followup_yes", now=NOW)
        await session.commit()

        assert question.followup_result == "yes"
        evidence = (
            (
                await session.execute(
                    select(AdoptionEvidence).where(AdoptionEvidence.teacher_id == teacher.id)
                )
            )
            .scalars()
            .all()
        )
        assert [(e.move_id, e.level, e.source) for e in evidence] == [
            ("NUM_PLACE_VALUE_BUNDLES", 2, "reflection")
        ]
        # nothing left awaiting an answer
        assert (
            await record_followup_from_button(session, teacher.id, "followup_yes", now=NOW) is False
        )


async def test_no_button_records_answer_without_evidence(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    async with factory() as session:
        cluster_id = await _cluster(session)
        teacher = await _teacher(session, cluster_id)
        question = await _question(session, teacher)
        await schedule_followup_for_question(
            session, question, now=DUE, move_id="NUM_PLACE_VALUE_BUNDLES"
        )
        await session.commit()
        assert await record_followup_from_button(session, teacher.id, "followup_no", now=NOW)
        await session.commit()
        assert question.followup_result == "no"
        count = (
            await session.execute(
                select(AdoptionEvidence).where(AdoptionEvidence.teacher_id == teacher.id)
            )
        ).first()
        assert count is None


# ── fast-forward ─────────────────────────────────────────────────────────


async def test_fast_forward_runs_only_that_teachers_pending_jobs(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    channel = FakeChannel()
    async with factory() as session:
        cluster_id = await _cluster(session)
        t1 = await _teacher(session, cluster_id, name="पहली")
        t2 = await _teacher(session, cluster_id, name="दूसरी")
        q1 = await _question(session, t1)
        q2 = await _question(session, t2)
        j1 = await schedule_followup_for_question(session, q1, now=NOW)  # due after the delay
        j2 = await schedule_followup_for_question(session, q2, now=NOW)
        await session.commit()

    result = await fast_forward_teacher(
        t1.id, session_factory=factory, clock=lambda: NOW, resolve_channel=lambda t: channel
    )

    assert result.advanced == 1
    assert [o.status for o in result.outcomes] == ["done"]
    assert [sent[0] for sent in channel.sent] == [t1.id]
    assert (await _reload(factory, j1.id)).status == "done"
    row2 = await _reload(factory, j2.id)
    assert row2.status == "pending" and row2.run_at == NOW + FOLLOWUP_DELAY


# ── planner ──────────────────────────────────────────────────────────────


async def test_planner_queues_aggregates_and_one_digest_per_arp_idempotently(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    async with factory() as session:
        cluster_id = await _cluster(session)
        arp = AppUser(
            id=uuid.uuid4(), username=f"jt-{uuid.uuid4().hex[:6]}", password_hash="x", role="arp"
        )
        session.add(arp)
        await session.flush()
        session.add(ARPAssignment(arp_user_id=arp.id, cluster_id=cluster_id))
        await session.commit()

    async with factory() as session:
        created = await plan_recurring_jobs(session, NOW)
        await session.commit()
    kinds = sorted(j.kind for j in created)
    assert "aggregates" in kinds and kinds.count("arp_digest") >= 1

    async with factory() as session:
        again = await plan_recurring_jobs(session, NOW)
        await session.commit()
    assert again == []

    async with factory() as session:
        jobs = (await session.execute(select(ScheduledJob))).scalars().all()
    aggregates = [j for j in jobs if j.kind == "aggregates"]
    digests = [
        j for j in jobs if j.kind == "arp_digest" and (j.payload or {})["cluster_id"] == cluster_id
    ]
    assert len(aggregates) == 1
    assert aggregates[0].run_at == datetime(2026, 10, 14, 20, 30, tzinfo=UTC)  # 02:00 IST
    assert len(digests) == 1
    assert digests[0].run_at == datetime(2026, 10, 17, 11, 30, tzinfo=UTC)  # Sat 17:00 IST


# ── arp_digest ───────────────────────────────────────────────────────────


async def test_arp_digest_snapshot_hides_non_consenting_teachers(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    async with factory() as session:
        cluster_id = await _cluster(session)
        shares = await _teacher(
            session, cluster_id, name="साझा करने वाली", consent_share_scores=True
        )
        private = await _teacher(
            session, cluster_id, name="निजी शिक्षिका", consent_share_scores=False
        )
        for teacher in (shares, private):
            session.add(
                SessionState(
                    teacher_id=teacher.id,
                    week_start=WEEK_START,
                    move_id="NUM_PLACE_VALUE_BUNDLES",
                    state="FEEDBACK",
                    rehearse_attempts=1,
                    context={},
                )
            )
        await _question(session, private, status="escalated", text="गुप्त सवाल")
        job = await _job(
            session, "arp_digest", NOW - timedelta(minutes=1), cluster_id=cluster_id, slot="x"
        )
        await session.commit()

    outcomes = await run_due_jobs(session_factory=factory, clock=lambda: NOW)
    assert [o.status for o in outcomes] == ["done"]

    async with factory() as session:
        snapshot = await latest_arp_digest_snapshot(session, cluster_id)
    assert snapshot is not None
    assert snapshot["week_start"] == "2026-10-12"
    digest = snapshot["digest"]
    assert digest["total_teachers"] == 2
    assert digest["active_teachers_count"] == 2
    assert digest["unanswered_questions_count"] == 1
    assert [d["teacher_name"] for d in digest["consenting_teacher_details"]] == ["साझा करने वाली"]
    rendered = str(snapshot)
    assert "निजी शिक्षिका" not in rendered and "गुप्त सवाल" not in rendered
    assert (await _reload(factory, job.id)).status == "done"


async def test_arp_digest_without_cluster_is_cancelled(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    async with factory() as session:
        await _job(session, "arp_digest", NOW - timedelta(minutes=1))
        await session.commit()
    outcomes = await run_due_jobs(session_factory=factory, clock=lambda: NOW)
    assert [o.status for o in outcomes] == ["cancelled"]


# ── aggregates ───────────────────────────────────────────────────────────


async def test_aggregates_upserts_one_row_per_batch_and_move(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    batch_id = f"jt-{uuid.uuid4().hex[:6]}"
    calls: list[tuple[str, str]] = []

    async def fake_compute(session: AsyncSession, batch: str, move: str) -> AggModuleBatch:
        calls.append((batch, move))
        return AggModuleBatch(batch_id=batch, move_id=move, n_teachers=len(calls), computed_at=NOW)

    async with factory() as session:
        session.add(Batch(id=batch_id, name="जाँच बैच"))
        cluster_id = await _cluster(session)
        teacher = await _teacher(session, cluster_id, batch_id=batch_id)
        session.add(
            SessionState(
                teacher_id=teacher.id,
                week_start=WEEK_START,
                move_id="MOVE_A",
                state="LEARN",
                context={},
            )
        )
        session.add(
            AdoptionEvidence(teacher_id=teacher.id, move_id="MOVE_B", level=1, source="rehearsal")
        )
        await session.commit()

    for _ in range(2):  # second run must update, not duplicate
        async with factory() as session:
            await _job(session, "aggregates", NOW - timedelta(minutes=1))
            await session.commit()
        outcomes = await run_due_jobs(
            session_factory=factory, clock=lambda: NOW, compute_aggregates=fake_compute
        )
        assert outcomes and all(o.status == "done" for o in outcomes)

    assert (batch_id, "MOVE_A") in calls and (batch_id, "MOVE_B") in calls
    async with factory() as session:
        rows = (
            (
                await session.execute(
                    select(AggModuleBatch).where(AggModuleBatch.batch_id == batch_id)
                )
            )
            .scalars()
            .all()
        )
    assert sorted(r.move_id for r in rows) == ["MOVE_A", "MOVE_B"]


# ── reminder & followup_try_in_class & retention_purge ───────────────────


async def test_reminder_job_runs_on_postgres(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    fake_ch = FakeChannel(freeform=True)
    async with factory() as session:
        cluster_id = await _cluster(session)
        teacher = await _teacher(
            session,
            cluster_id,
            name="सुनीता",
            last_inbound_at=NOW - timedelta(hours=80),
        )
        session.add(
            SessionState(
                teacher_id=teacher.id,
                week_start=WEEK_START,
                move_id="MOVE_A",
                state="REHEARSE",
                context={},
            )
        )
        job = await _job(
            session,
            KIND_REMINDER,
            NOW - timedelta(minutes=1),
            teacher_id=str(teacher.id),
            slot="2026-10-14",
        )
        await session.commit()

    outcomes = await run_due_jobs(
        session_factory=factory,
        clock=lambda: NOW,
        resolve_channel=lambda t: fake_ch,
    )
    assert len(outcomes) == 1
    assert outcomes[0].status == "done"
    assert (await _reload(factory, job.id)).status == "done"
    assert len(fake_ch.sent) == 1
    sent_msgs = fake_ch.sent[0][1]
    assert len(sent_msgs) == 1
    assert sent_msgs[0].kind == "buttons"


async def test_followup_try_in_class_job_runs_on_postgres(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    fake_ch = FakeChannel(freeform=True)
    async with factory() as session:
        cluster_id = await _cluster(session)
        teacher = await _teacher(session, cluster_id, name="सुनीता")
        session.add(
            SessionState(
                teacher_id=teacher.id,
                week_start=WEEK_START,
                move_id="MOVE_A",
                state="TRY_IN_CLASS",
                context={},
            )
        )
        job = await _job(
            session,
            KIND_FOLLOWUP_TRY_IN_CLASS,
            NOW - timedelta(minutes=1),
            teacher_id=str(teacher.id),
            move_id="MOVE_A",
            slot="2026-10-14",
        )
        await session.commit()

    outcomes = await run_due_jobs(
        session_factory=factory,
        clock=lambda: NOW,
        resolve_channel=lambda t: fake_ch,
    )
    assert len(outcomes) == 1
    assert outcomes[0].status == "done"
    assert (await _reload(factory, job.id)).status == "done"
    assert len(fake_ch.sent) == 1
    buttons = [b.id for b in (fake_ch.sent[0][1][0].buttons or [])]
    assert "btn_peer" in buttons
    assert "btn_self" in buttons


async def test_retention_purge_job_runs_on_postgres(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    async with factory() as session:
        cluster_id = await _cluster(session)
        # 1. Demo teacher (must never be touched)
        demo_t = await _teacher(session, cluster_id, name="डेमो शिक्षक", is_demo=True)
        demo_turn = Turn(
            id=uuid.uuid4(),
            teacher_id=demo_t.id,
            idx=0,
            role="teacher",
            transcript="डेमो सुरक्षित पाठ",
            created_at=NOW - timedelta(days=120),
        )
        session.add(demo_turn)

        # 2. Non-demo teacher with old activity (> 90 days)
        old_t = await _teacher(session, cluster_id, name="पुराना शिक्षक", is_demo=False)
        old_turn = Turn(
            id=uuid.uuid4(),
            teacher_id=old_t.id,
            idx=0,
            role="teacher",
            transcript="पुराना पाठ जो मिटना चाहिए",
            created_at=NOW - timedelta(days=120),
        )
        session.add(old_turn)

        # 3. Non-demo teacher who withdrew consent > 24 h ago
        withdrawn_t = await _teacher(
            session,
            cluster_id,
            name="सहमति वापस ली",
            is_demo=False,
            consent_service=False,
            last_inbound_at=NOW - timedelta(hours=30),
        )
        withdrawn_turn = Turn(
            id=uuid.uuid4(),
            teacher_id=withdrawn_t.id,
            idx=0,
            role="teacher",
            transcript="सहमति रद्द वाला पाठ",
            created_at=NOW - timedelta(days=5),
        )
        session.add(withdrawn_turn)

        # 4. Retention purge job
        job = await _job(
            session,
            KIND_RETENTION_PURGE,
            NOW - timedelta(minutes=1),
            slot="2026-10-14",
        )
        await session.commit()

    outcomes = await run_due_jobs(session_factory=factory, clock=lambda: NOW)
    assert len(outcomes) == 1
    assert outcomes[0].status == "done"
    assert (await _reload(factory, job.id)).status == "done"

    async with factory() as session:
        reloaded_demo_turn = await session.get(Turn, demo_turn.id)
        assert reloaded_demo_turn is not None
        assert reloaded_demo_turn.transcript == "डेमो सुरक्षित पाठ"

        reloaded_old_turn = await session.get(Turn, old_turn.id)
        assert reloaded_old_turn is not None
        assert reloaded_old_turn.transcript is None

        reloaded_withdrawn_turn = await session.get(Turn, withdrawn_turn.id)
        assert reloaded_withdrawn_turn is not None
        assert reloaded_withdrawn_turn.transcript is None
