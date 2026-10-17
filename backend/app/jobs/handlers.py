"""Scheduled job handlers (spec/08 §8.6, spec/14 T24).

Scope (simplified per T24): `followup_question`, `arp_digest` snapshot and
`aggregates`. Sending always goes through the `Channel` protocol and every
teacher-facing string comes from `content/messages_hi.yaml`.

Delivery is at-least-once: a message is sent as the last step of a handler and
the job row is marked done in the transaction that follows, so a crash between
the two can repeat a send but can never lose one.
"""

from __future__ import annotations

import importlib
import logging
import uuid
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any, Final, cast

from sqlalchemy import ColumnElement, delete, or_, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.channels.base import Channel
from backend.app.config import settings
from backend.app.core.messages import get_message, has_message
from backend.app.core.types import Button, OutboundMessage
from backend.app.db.models import (
    AdoptionEvidence,
    AggModuleBatch,
    ARPAssignment,
    Message,
    Question,
    RehearsalScore,
    ScheduledJob,
    SessionState,
    Teacher,
    Turn,
)
from backend.app.jobs import schedule, tunables
from backend.app.reports.arp_digest import generate_arp_digest
from backend.app.sessions.state_machine import SessionStateEnum

logger = logging.getLogger("abhyas.jobs.handlers")

KIND_FOLLOWUP_QUESTION: Final = "followup_question"
KIND_ARP_DIGEST: Final = "arp_digest"
KIND_AGGREGATES: Final = "aggregates"
KIND_REMINDER: Final = "reminder"
KIND_FOLLOWUP_TRY_IN_CLASS: Final = "followup_try_in_class"
KIND_RETENTION_PURGE: Final = "retention_purge"

TEMPLATE_FOLLOWUP_QUESTION: Final = "tpl_followup_question"
TEMPLATE_REMINDER: Final = "tpl_reminder"
TEMPLATE_TRY_IN_CLASS_FOLLOWUP: Final = "tpl_try_in_class_followup"

# (button id, messages_hi.yaml key); titles always come from the catalog.
FOLLOWUP_BUTTONS: Final = (
    ("followup_yes", "btn_yes"),
    ("followup_no", "btn_decline"),
    ("followup_not_now", "btn_not_now"),
)
FOLLOWUP_BUTTON_RESULTS: Final = {
    "followup_yes": "yes",
    "followup_no": "no",
    "followup_not_now": "not_now",
}
FOLLOWUP_ELIGIBLE_STATUSES: Final = frozenset({"answered", "arp_answered"})

EVIDENCE_LEVEL_SELF_REPORTED: Final = 2

_REHEARSED_STATES: Final = frozenset(
    {
        SessionStateEnum.REHEARSE.value,
        SessionStateEnum.FEEDBACK.value,
        SessionStateEnum.TRY_IN_CLASS.value,
        SessionStateEnum.REFLECT_PEER.value,
        SessionStateEnum.REFLECT_SELF.value,
        SessionStateEnum.DONE.value,
    }
)
_REHEARSAL_COMPLETE_STATES: Final = frozenset(
    {
        SessionStateEnum.FEEDBACK.value,
        SessionStateEnum.TRY_IN_CLASS.value,
        SessionStateEnum.REFLECT_PEER.value,
        SessionStateEnum.REFLECT_SELF.value,
        SessionStateEnum.DONE.value,
    }
)

ChannelResolver = Callable[[Teacher], Channel]
ComputeAggregates = Callable[[AsyncSession, str, str], Awaitable[AggModuleBatch]]


class JobSkipped(Exception):
    """Raised by a handler when the job no longer applies; the row becomes `cancelled`."""


@dataclass(slots=True)
class JobContext:
    """Everything a handler needs, injected so tests can fake the clock and channels."""

    session: AsyncSession
    now: datetime
    resolve_channel: ChannelResolver
    compute_aggregates: ComputeAggregates | None = None


JobHandler = Callable[[JobContext, ScheduledJob], Awaitable[None]]


def default_channel_resolver(teacher: Teacher) -> Channel:
    """Web channel by default; WhatsApp only when enabled (mocks-first, AGENTS rule 5)."""
    if teacher.preferred_channel == "whatsapp" and settings.WHATSAPP_ENABLED:
        # Lane C's WhatsApp channel; imported lazily so lanes merge independently.
        module = importlib.import_module("backend.app.channels.whatsapp")
        return cast(Channel, module.WhatsAppChannel())
    from backend.app.channels.web import WebChannel

    return WebChannel()


def _payload(job: ScheduledJob) -> dict[str, Any]:
    return dict(job.payload or {})


def _payload_text(key: str) -> ColumnElement[str]:
    """`payload ->> key` (JSONB `.astext`), for idempotency and lookup queries."""
    payload: Any = ScheduledJob.payload
    return cast("ColumnElement[str]", payload[key].astext)


def _uuid_field(payload: Mapping[str, Any], key: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(payload[key]))
    except (KeyError, ValueError) as exc:
        raise JobSkipped(f"payload.{key} missing or invalid") from exc


# ── followup_question ────────────────────────────────────────────────────


def build_followup_messages(
    *, name: str, topic: str, address_form: str, freeform: bool
) -> list[OutboundMessage]:
    """Follow-up prompt: freeform with buttons inside the 24 h window, else the template."""
    if not freeform:
        return [
            OutboundMessage(
                kind="template",
                template_name=TEMPLATE_FOLLOWUP_QUESTION,
                template_params=[name, topic],
                speaker="abhyas",
            )
        ]
    buttons = [
        Button(id=button_id, title_hi=get_message(key))
        for button_id, key in FOLLOWUP_BUTTONS
        if has_message(key)
    ]
    text = get_message("followup_question", address_form=address_form, name=name, topic=topic)
    return [OutboundMessage(kind="buttons", text_hi=text, buttons=buttons, speaker="abhyas")]


async def handle_followup_question(ctx: JobContext, job: ScheduledJob) -> None:
    payload = _payload(job)
    question = await ctx.session.get(Question, _uuid_field(payload, "question_id"))
    if question is None:
        raise JobSkipped("question not found")
    if question.followup_result is not None:
        raise JobSkipped("follow-up already answered")
    if question.status not in FOLLOWUP_ELIGIBLE_STATUSES:
        raise JobSkipped(f"question status is {question.status}")

    teacher = await ctx.session.get(Teacher, question.teacher_id)
    if teacher is None:
        raise JobSkipped("teacher not found")
    if not teacher.consent_service:
        raise JobSkipped("teacher has not consented to the service")
    if not teacher.name:
        raise JobSkipped("teacher has no name for the greeting")

    channel = ctx.resolve_channel(teacher)
    freeform = await channel.can_send_freeform(teacher)
    topic = schedule.truncate_words(question.text, tunables.FOLLOWUP_TOPIC_MAX_WORDS)
    messages = build_followup_messages(
        name=teacher.name, topic=topic, address_form=teacher.address_form, freeform=freeform
    )
    await channel.send(teacher, messages)
    job.payload = {
        **payload,
        "sent_at": ctx.now.isoformat(),
        "mode": "freeform" if freeform else "template",
    }


async def schedule_followup_for_question(
    session: AsyncSession, question: Question, *, now: datetime, move_id: str | None = None
) -> ScheduledJob:
    """Called by the ASK flow after answering: queue the +48 h follow-up. Caller commits."""
    run_at = now + timedelta(hours=tunables.FOLLOWUP_HOURS)
    question.followup_at = run_at
    job = ScheduledJob(
        kind=KIND_FOLLOWUP_QUESTION,
        run_at=run_at,
        payload={
            "question_id": str(question.id),
            "teacher_id": str(question.teacher_id),
            "move_id": move_id,
        },
    )
    session.add(job)
    return job


async def record_followup_from_button(
    session: AsyncSession, teacher_id: uuid.UUID, button_id: str | None, *, now: datetime
) -> bool:
    """Called for inbound buttons: store the answer on the question; 'yes' → evidence level 2.

    Returns False when the button is not a follow-up button or no follow-up is awaiting one.
    """
    result = FOLLOWUP_BUTTON_RESULTS.get(button_id or "")
    if result is None:
        return False
    question = (
        await session.execute(
            select(Question)
            .where(
                Question.teacher_id == teacher_id,
                Question.followup_at.is_not(None),
                Question.followup_at <= now,
                Question.followup_result.is_(None),
            )
            .order_by(Question.followup_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if question is None:
        return False

    question.followup_result = result
    if result == "yes":
        job = (
            await session.execute(
                select(ScheduledJob)
                .where(
                    ScheduledJob.kind == KIND_FOLLOWUP_QUESTION,
                    _payload_text("question_id") == str(question.id),
                )
                .order_by(ScheduledJob.run_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        move_id = (job.payload or {}).get("move_id") if job is not None else None
        if move_id:
            session.add(
                AdoptionEvidence(
                    teacher_id=teacher_id,
                    move_id=str(move_id),
                    level=EVIDENCE_LEVEL_SELF_REPORTED,
                    source="reflection",
                    detail={"via": KIND_FOLLOWUP_QUESTION, "question_id": str(question.id)},
                )
            )
    return True


# ── arp_digest ───────────────────────────────────────────────────────────


def _low_criteria(scores: Mapping[str, Any]) -> list[str]:
    """Rubric criteria scored 0 (rubric is 0–2); tolerates {id: n} and {id: {"score": n}}."""
    low: list[str] = []
    for criterion, raw in scores.items():
        value = raw.get("score") if isinstance(raw, Mapping) else raw
        if isinstance(value, int) and not isinstance(value, bool) and value == 0:
            low.append(str(criterion))
    return sorted(low)


async def _digest_rows(
    session: AsyncSession, cluster_id: str, week_start: date
) -> list[dict[str, Any]]:
    """One dict per teacher in the cluster, in the shape `generate_arp_digest` expects."""
    teachers = (
        (
            await session.execute(
                select(Teacher).where(
                    Teacher.cluster_id == cluster_id, Teacher.consent_service.is_(True)
                )
            )
        )
        .scalars()
        .all()
    )
    if not teachers:
        return []
    ids = [t.id for t in teachers]

    states = {
        s.teacher_id: s
        for s in (
            await session.execute(
                select(SessionState).where(
                    SessionState.teacher_id.in_(ids), SessionState.week_start == week_start
                )
            )
        )
        .scalars()
        .all()
    }
    escalated: dict[uuid.UUID, list[str]] = {}
    for q in (
        (
            await session.execute(
                select(Question).where(Question.teacher_id.in_(ids), Question.status == "escalated")
            )
        )
        .scalars()
        .all()
    ):
        escalated.setdefault(q.teacher_id, []).append(q.text)

    latest_scores: dict[uuid.UUID, RehearsalScore] = {}
    for score in (
        (
            await session.execute(
                select(RehearsalScore)
                .where(RehearsalScore.teacher_id.in_(ids))
                .order_by(RehearsalScore.created_at.desc())
            )
        )
        .scalars()
        .all()
    ):
        state = states.get(score.teacher_id)
        if state is not None and score.move_id == state.move_id:
            latest_scores.setdefault(score.teacher_id, score)

    rows: list[dict[str, Any]] = []
    for teacher in teachers:
        state = states.get(teacher.id)
        teacher_score = latest_scores.get(teacher.id)
        struggled = _low_criteria(teacher_score.scores) if teacher_score is not None else []
        questions = escalated.get(teacher.id, [])
        rows.append(
            {
                "name": teacher.name or "",
                "consent_share_scores": teacher.consent_share_scores,
                "move_id": state.move_id if state is not None else "N/A",
                "practised_this_week": state is not None
                and (state.rehearse_attempts > 0 or state.state in _REHEARSED_STATES),
                "rehearsal_completed": state is not None
                and state.state in _REHEARSAL_COMPLETE_STATES,
                "struggled_on": struggled,
                "questions": questions,
                "needs_visit_support": bool(struggled or questions),
            }
        )
    return rows


async def handle_arp_digest(ctx: JobContext, job: ScheduledJob) -> None:
    """Builds the consent-filtered weekly snapshot and stores it on the job row.

    `generate_arp_digest` owns the privacy filtering (names, scores and question text
    only for `consent_share_scores`). ARPs are `app_user` rows with no stored contact,
    so no WhatsApp send happens here; the `/arp` page reads the snapshot.
    """
    payload = _payload(job)
    cluster_id = payload.get("cluster_id")
    if not isinstance(cluster_id, str) or not cluster_id:
        raise JobSkipped("payload.cluster_id missing")

    week_start = schedule.week_start_ist(ctx.now)
    rows = await _digest_rows(ctx.session, cluster_id, week_start)
    digest = generate_arp_digest(cluster_id, rows)
    job.payload = {
        **payload,
        "snapshot": {
            "cluster_id": cluster_id,
            "week_start": week_start.isoformat(),
            "built_at": ctx.now.isoformat(),
            "digest": digest.model_dump(mode="json"),
        },
    }


async def latest_arp_digest_snapshot(
    session: AsyncSession, cluster_id: str
) -> dict[str, Any] | None:
    """Most recent completed digest snapshot for a cluster (for the `/arp` page)."""
    job = (
        await session.execute(
            select(ScheduledJob)
            .where(
                ScheduledJob.kind == KIND_ARP_DIGEST,
                ScheduledJob.status == "done",
                _payload_text("cluster_id") == cluster_id,
            )
            .order_by(ScheduledJob.run_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    snapshot = (job.payload or {}).get("snapshot") if job is not None else None
    return snapshot if isinstance(snapshot, dict) else None


# ── aggregates ───────────────────────────────────────────────────────────


def _load_compute_aggregates() -> ComputeAggregates:
    """Lane C owns jobs/aggregates.py (T31 stub, real job is this T24); import lazily."""
    try:
        module = importlib.import_module("backend.app.jobs.aggregates")
    except ImportError as exc:
        raise RuntimeError(
            "backend.app.jobs.aggregates is not on this branch yet; "
            "merge lane-c's compute_aggregates_for_batch before the aggregates job can run"
        ) from exc
    return cast(ComputeAggregates, module.compute_aggregates_for_batch)


async def _batch_move_pairs(session: AsyncSession) -> list[tuple[str, str]]:
    """Distinct (batch, move) pairs that have session or evidence activity."""
    from_sessions = (
        select(Teacher.batch_id, SessionState.move_id)
        .select_from(Teacher)
        .join(SessionState, SessionState.teacher_id == Teacher.id)
        .where(Teacher.batch_id.is_not(None))
        .distinct()
    )
    from_evidence = (
        select(Teacher.batch_id, AdoptionEvidence.move_id)
        .select_from(Teacher)
        .join(AdoptionEvidence, AdoptionEvidence.teacher_id == Teacher.id)
        .where(Teacher.batch_id.is_not(None))
        .distinct()
    )
    pairs: set[tuple[str, str]] = set()
    for stmt in (from_sessions, from_evidence):
        for batch_id, move_id in (await session.execute(stmt)).all():
            if batch_id is not None and move_id:
                pairs.add((str(batch_id), str(move_id)))
    return sorted(pairs)


async def handle_aggregates(ctx: JobContext, job: ScheduledJob) -> None:
    """Recomputes `agg_module_batch` for every (batch, move) that has activity."""
    compute = ctx.compute_aggregates or _load_compute_aggregates()
    pairs = await _batch_move_pairs(ctx.session)
    for batch_id, move_id in pairs:
        aggregate = await compute(ctx.session, batch_id, move_id)
        await ctx.session.merge(aggregate)
    job.payload = {**_payload(job), "pairs": len(pairs), "computed_at": ctx.now.isoformat()}


# ── reminder ─────────────────────────────────────────────────────────────


async def handle_reminder(ctx: JobContext, job: ScheduledJob) -> None:
    """Sends a gentle nudge if teacher has not interacted in REMINDER_HOURS (spec/08 §8.5, §8.6)."""
    payload = _payload(job)
    teacher_id = _uuid_field(payload, "teacher_id")
    teacher = await ctx.session.get(Teacher, teacher_id)
    if teacher is None:
        raise JobSkipped("teacher not found")
    if not teacher.consent_service:
        raise JobSkipped("teacher has not consented to the service")
    if not teacher.name:
        raise JobSkipped("teacher has no name for the greeting")

    week_start = schedule.week_start_ist(ctx.now)
    stmt = select(SessionState).where(
        SessionState.teacher_id == teacher.id,
        SessionState.week_start == week_start,
    )
    session_state = (await ctx.session.execute(stmt)).scalar_one_or_none()
    if session_state is None:
        raise JobSkipped("no active session for the current week")
    if session_state.state == SessionStateEnum.DONE.value:
        raise JobSkipped("teacher already completed the weekly loop")

    if teacher.last_inbound_at is not None:
        elapsed = ctx.now - teacher.last_inbound_at
        if elapsed < timedelta(hours=tunables.REMINDER_HOURS):
            raise JobSkipped("teacher has interacted recently")

    # Enforce maximum 1 reminder per week
    week_start_dt = datetime.combine(
        week_start, datetime.min.time(), tzinfo=schedule.IST
    ).astimezone(UTC)
    stmt_rem = select(ScheduledJob).where(
        ScheduledJob.kind == KIND_REMINDER,
        ScheduledJob.status == "done",
        _payload_text("teacher_id") == str(teacher.id),
        ScheduledJob.run_at >= week_start_dt,
        ScheduledJob.id != job.id,
    )
    if (await ctx.session.execute(stmt_rem)).scalar_one_or_none() is not None:
        raise JobSkipped("already sent a reminder this week")

    channel = ctx.resolve_channel(teacher)
    freeform = await channel.can_send_freeform(teacher)
    if freeform:
        text_hi = get_message(
            "reminder",
            name=teacher.name,
            address_form=teacher.address_form,
        )
        buttons = [
            Button(
                id="btn_continue",
                title_hi=get_message("btn_continue", address_form=teacher.address_form),
            ),
            Button(
                id="btn_restart",
                title_hi=get_message("btn_restart", address_form=teacher.address_form),
            ),
        ]
        messages = [
            OutboundMessage(kind="buttons", text_hi=text_hi, buttons=buttons, speaker="abhyas")
        ]
    else:
        messages = [
            OutboundMessage(
                kind="template",
                template_name=TEMPLATE_REMINDER,
                template_params=[teacher.name],
                speaker="abhyas",
            )
        ]

    await channel.send(teacher, messages)
    job.payload = {
        **payload,
        "sent_at": ctx.now.isoformat(),
        "mode": "freeform" if freeform else "template",
    }


async def schedule_reminder(
    session: AsyncSession | None,
    teacher_id: uuid.UUID,
    *,
    now: datetime,
) -> ScheduledJob | None:
    """Queues a reminder job for teacher_id +REMINDER_HOURS ahead with IST date slot dedupe."""
    if session is None:
        return None
    run_at = now + timedelta(hours=tunables.REMINDER_HOURS)
    slot = schedule.to_ist(run_at).date().isoformat()
    existing = await session.execute(
        select(ScheduledJob).where(
            ScheduledJob.kind == KIND_REMINDER,
            _payload_text("teacher_id") == str(teacher_id),
            _payload_text("slot") == slot,
            ScheduledJob.status != "cancelled",
        )
    )
    if existing.scalars().first() is not None:
        return None

    job = ScheduledJob(
        kind=KIND_REMINDER,
        run_at=run_at,
        payload={
            "teacher_id": str(teacher_id),
            "slot": slot,
        },
    )
    session.add(job)
    return job


# ── followup_try_in_class ────────────────────────────────────────────────


async def handle_followup_try_in_class(ctx: JobContext, job: ScheduledJob) -> None:
    """Prompts teacher to reflect or share evidence after TRY_IN_CLASS (spec/08 §8.5, §8.6)."""
    payload = _payload(job)
    teacher_id = _uuid_field(payload, "teacher_id")
    move_id = str(payload.get("move_id") or "")
    if not move_id:
        raise JobSkipped("payload.move_id missing")

    teacher = await ctx.session.get(Teacher, teacher_id)
    if teacher is None:
        raise JobSkipped("teacher not found")
    if not teacher.consent_service:
        raise JobSkipped("teacher has not consented to the service")
    if not teacher.name:
        raise JobSkipped("teacher has no name for the greeting")

    stmt = (
        select(SessionState)
        .where(SessionState.teacher_id == teacher.id)
        .order_by(SessionState.week_start.desc())
        .limit(1)
    )
    session_state = (await ctx.session.execute(stmt)).scalar_one_or_none()
    if session_state is None:
        raise JobSkipped("no active session for teacher")
    if session_state.state != SessionStateEnum.TRY_IN_CLASS.value:
        raise JobSkipped(f"teacher no longer in TRY_IN_CLASS, state is {session_state.state}")

    stmt_ev = select(AdoptionEvidence).where(
        AdoptionEvidence.teacher_id == teacher.id,
        AdoptionEvidence.move_id == move_id,
        AdoptionEvidence.level >= 2,
    )
    if (await ctx.session.execute(stmt_ev)).scalars().first() is not None:
        raise JobSkipped("evidence level >= 2 already recorded for this move")

    try:
        from backend.app.rehearsal.scene_runner import load_move_card

        move_card = load_move_card(move_id)
        move_title = move_card.title_hi
    except (FileNotFoundError, ValueError, OSError):
        move_title = move_id

    channel = ctx.resolve_channel(teacher)
    freeform = await channel.can_send_freeform(teacher)
    if freeform:
        text_hi = get_message(
            "followup_try_in_class",
            name=teacher.name,
            move_title=move_title,
            address_form=teacher.address_form,
        )
        buttons = [
            Button(
                id="btn_peer", title_hi=get_message("btn_peer", address_form=teacher.address_form)
            ),
            Button(
                id="btn_self", title_hi=get_message("btn_self", address_form=teacher.address_form)
            ),
            Button(
                id="btn_later", title_hi=get_message("btn_later", address_form=teacher.address_form)
            ),
        ]
        messages = [
            OutboundMessage(kind="buttons", text_hi=text_hi, buttons=buttons, speaker="abhyas")
        ]
    else:
        messages = [
            OutboundMessage(
                kind="template",
                template_name=TEMPLATE_TRY_IN_CLASS_FOLLOWUP,
                template_params=[teacher.name, move_title],
                speaker="abhyas",
            )
        ]

    await channel.send(teacher, messages)
    job.payload = {
        **payload,
        "sent_at": ctx.now.isoformat(),
        "mode": "freeform" if freeform else "template",
    }


async def schedule_followup_try_in_class(
    session: AsyncSession | None,
    teacher_id: uuid.UUID,
    move_id: str,
    *,
    now: datetime,
) -> ScheduledJob | None:
    """Queues a followup_try_in_class job +FOLLOWUP_TRY_IN_CLASS_HOURS ahead with IST date slot dedupe."""
    if session is None:
        return None
    run_at = now + timedelta(hours=tunables.FOLLOWUP_TRY_IN_CLASS_HOURS)
    slot = schedule.to_ist(run_at).date().isoformat()
    existing = await session.execute(
        select(ScheduledJob).where(
            ScheduledJob.kind == KIND_FOLLOWUP_TRY_IN_CLASS,
            _payload_text("teacher_id") == str(teacher_id),
            _payload_text("move_id") == str(move_id),
            _payload_text("slot") == slot,
            ScheduledJob.status != "cancelled",
        )
    )
    if existing.scalars().first() is not None:
        return None

    job = ScheduledJob(
        kind=KIND_FOLLOWUP_TRY_IN_CLASS,
        run_at=run_at,
        payload={
            "teacher_id": str(teacher_id),
            "move_id": str(move_id),
            "slot": slot,
        },
    )
    session.add(job)
    return job


# ── retention_purge ──────────────────────────────────────────────────────


async def handle_retention_purge(ctx: JobContext, job: ScheduledJob) -> None:
    """Purges transcripts and message texts past retention window; never touches demo teachers; logs counts only."""
    cutoff = ctx.now - timedelta(days=tunables.DATA_RETENTION_DAYS)

    # Demo teacher IDs must NEVER be touched
    demo_ids = list(
        (await ctx.session.execute(select(Teacher.id).where(Teacher.is_demo.is_(True))))
        .scalars()
        .all()
    )

    # Non-demo teachers who withdrew consent > 24 h ago
    withdrawn_cutoff = ctx.now - timedelta(hours=24)
    stmt_withdrawn = select(Teacher.id).where(
        Teacher.consent_service.is_(False),
        Teacher.is_demo.is_(False),
        (Teacher.last_inbound_at <= withdrawn_cutoff) | (Teacher.last_inbound_at.is_(None)),
    )
    withdrawn_ids = list((await ctx.session.execute(stmt_withdrawn)).scalars().all())

    # Build targets for transcript and message purge
    purge_teacher_filters: list[ColumnElement[bool]] = []
    if withdrawn_ids:
        purge_teacher_filters.append(Turn.teacher_id.in_(withdrawn_ids))
    purge_teacher_filters.append(Turn.created_at < cutoff)

    turn_where: list[ColumnElement[bool]] = [Turn.transcript.is_not(None)]
    if demo_ids:
        turn_where.append(Turn.teacher_id.not_in(demo_ids))
    turn_where.append(or_(*purge_teacher_filters))

    res_turns = await ctx.session.execute(update(Turn).where(*turn_where).values(transcript=None))
    purged_turns = (
        res_turns.rowcount
        if isinstance(res_turns, CursorResult)
        and res_turns.rowcount is not None
        and res_turns.rowcount >= 0
        else 0
    )

    msg_teacher_filters: list[ColumnElement[bool]] = []
    if withdrawn_ids:
        msg_teacher_filters.append(Message.teacher_id.in_(withdrawn_ids))
    msg_teacher_filters.append(Message.created_at < cutoff)

    msg_where: list[ColumnElement[bool]] = [Message.text.is_not(None)]
    if demo_ids:
        msg_where.append(Message.teacher_id.not_in(demo_ids))
    msg_where.append(or_(*msg_teacher_filters))

    res_messages = await ctx.session.execute(update(Message).where(*msg_where).values(text=None))
    purged_messages = (
        res_messages.rowcount
        if isinstance(res_messages, CursorResult)
        and res_messages.rowcount is not None
        and res_messages.rowcount >= 0
        else 0
    )

    res_jobs = await ctx.session.execute(
        delete(ScheduledJob).where(
            ScheduledJob.status.in_(["done", "cancelled"]),
            ScheduledJob.run_at < cutoff,
            ScheduledJob.id != job.id,
        )
    )
    deleted_jobs = (
        res_jobs.rowcount
        if isinstance(res_jobs, CursorResult)
        and res_jobs.rowcount is not None
        and res_jobs.rowcount >= 0
        else 0
    )

    logger.info(
        "retention_purge completed: purged %d turn transcripts, %d message texts, %d expired scheduled jobs (cutoff: %s)",
        purged_turns,
        purged_messages,
        deleted_jobs,
        cutoff.date().isoformat(),
    )

    payload = _payload(job)
    job.payload = {
        **payload,
        "purged_at": ctx.now.isoformat(),
        "purged_turns": purged_turns,
        "purged_messages": purged_messages,
        "deleted_jobs": deleted_jobs,
    }


# ── recurring-job planner ────────────────────────────────────────────────


async def _slot_rows(session: AsyncSession, kind: str, slot: str) -> list[ScheduledJob]:
    stmt = select(ScheduledJob).where(
        ScheduledJob.kind == kind,
        _payload_text("slot") == slot,
        ScheduledJob.status != "cancelled",
    )
    return list((await session.execute(stmt)).scalars().all())


async def plan_recurring_jobs(session: AsyncSession, now: datetime) -> list[ScheduledJob]:
    """Idempotently queues the next nightly aggregates run, Saturday digest, and nightly retention purge.

    Dedupes on a `slot` (IST date) in the payload, so it is safe to call on every start
    and on a timer; caller commits. Replaces the spec's "daily planner job" because it
    needs no bootstrap row and survives restarts.
    """
    created: list[ScheduledJob] = []

    aggregates_at = schedule.next_daily_at(now, tunables.AGGREGATES_HOUR_IST)
    aggregates_slot = schedule.to_ist(aggregates_at).date().isoformat()
    if not await _slot_rows(session, KIND_AGGREGATES, aggregates_slot):
        created.append(
            ScheduledJob(
                kind=KIND_AGGREGATES, run_at=aggregates_at, payload={"slot": aggregates_slot}
            )
        )

    purge_at = schedule.next_daily_at(now, tunables.RETENTION_PURGE_HOUR_IST)
    purge_slot = schedule.to_ist(purge_at).date().isoformat()
    if not await _slot_rows(session, KIND_RETENTION_PURGE, purge_slot):
        created.append(
            ScheduledJob(
                kind=KIND_RETENTION_PURGE,
                run_at=purge_at,
                payload={"slot": purge_slot},
            )
        )

    digest_at = schedule.next_weekly_at(
        now, tunables.ARP_DIGEST_WEEKDAY, tunables.ARP_DIGEST_HOUR_IST
    )
    digest_slot = schedule.to_ist(digest_at).date().isoformat()
    queued = {
        (str(p.get("arp_user_id")), str(p.get("cluster_id")))
        for p in (_payload(j) for j in await _slot_rows(session, KIND_ARP_DIGEST, digest_slot))
    }
    for assignment in (await session.execute(select(ARPAssignment))).scalars().all():
        key = (str(assignment.arp_user_id), assignment.cluster_id)
        if key not in queued:
            created.append(
                ScheduledJob(
                    kind=KIND_ARP_DIGEST,
                    run_at=digest_at,
                    payload={
                        "arp_user_id": key[0],
                        "cluster_id": key[1],
                        "slot": digest_slot,
                    },
                )
            )

    session.add_all(created)
    return created


HANDLERS: Final[Mapping[str, JobHandler]] = {
    KIND_FOLLOWUP_QUESTION: handle_followup_question,
    KIND_ARP_DIGEST: handle_arp_digest,
    KIND_AGGREGATES: handle_aggregates,
    KIND_REMINDER: handle_reminder,
    KIND_FOLLOWUP_TRY_IN_CLASS: handle_followup_try_in_class,
    KIND_RETENTION_PURGE: handle_retention_purge,
}
