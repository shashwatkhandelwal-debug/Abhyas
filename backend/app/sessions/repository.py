"""Repository for Session, Teacher, and Evidence database persistence (spec/03, spec/08)."""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models import (
    AdoptionEvidence,
    ClassOutcome,
    ConsentLog,
    ExplainScore,
    InviteCode,
    ModuleProgress,
    MovePath,
    Question,
    RealismRating,
    RehearsalScore,
    ReviewItem,
    SessionState,
    Teacher,
    TrainingRating,
)
from backend.app.sessions.path import MovePathEntry

logger = logging.getLogger("abhyas.sessions.repository")


class SessionRepository:
    """Manages database persistence for sessions, teachers, and evidence."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_or_create_teacher(self, teacher_id: UUID) -> Teacher:
        """Retrieves an existing teacher or creates an initial record."""
        res = await self.session.execute(select(Teacher).where(Teacher.id == teacher_id))
        teacher = res.scalar_one_or_none()
        if teacher is not None:
            return teacher

        teacher = Teacher(
            id=teacher_id,
            onboarding_state="NEW",
            address_form="f",
            preferred_channel="whatsapp",
            lite_mode=False,
            consent_service=False,
            consent_share_scores=False,
            created_at=datetime.now(UTC),
        )
        try:
            async with self.session.begin_nested():
                self.session.add(teacher)
                await self.session.flush()
            await self.session.commit()
        except IntegrityError:
            res = await self.session.execute(select(Teacher).where(Teacher.id == teacher_id))
            return res.scalar_one()

        return teacher

    async def save_teacher(self, teacher: Teacher) -> None:
        """Persists updated teacher attributes."""
        self.session.add(teacher)
        await self.session.commit()

    async def get_or_create_session_state(
        self, teacher_id: UUID, week_start: date, move_id: str
    ) -> SessionState:
        """Retrieves or creates weekly SessionState."""
        res = await self.session.execute(
            select(SessionState).where(
                SessionState.teacher_id == teacher_id,
                SessionState.week_start == week_start,
            )
        )
        state = res.scalar_one_or_none()
        if state is not None:
            return state

        st = SessionState(
            teacher_id=teacher_id,
            week_start=week_start,
            move_id=move_id,
            state="LEARN",
            prior_state=None,
            rehearse_attempts=0,
            context={},
            updated_at=datetime.now(UTC),
        )
        try:
            async with self.session.begin_nested():
                self.session.add(st)
                await self.session.flush()
            await self.session.commit()
        except IntegrityError:
            res = await self.session.execute(
                select(SessionState).where(
                    SessionState.teacher_id == teacher_id,
                    SessionState.week_start == week_start,
                )
            )
            return res.scalar_one()

        return st

    async def save_session_state(self, session_state: SessionState) -> None:
        """Persists updated session_state."""
        session_state.updated_at = datetime.now(UTC)
        self.session.add(session_state)
        await self.session.commit()

    async def get_invite_code(self, code: str) -> InviteCode | None:
        """Looks up an invite code (case-insensitive)."""
        norm_code = code.strip().upper()
        res = await self.session.execute(
            select(InviteCode).where(InviteCode.code == norm_code, InviteCode.active.is_(True))
        )
        return res.scalar_one_or_none()

    async def log_consent(
        self, teacher_id: UUID, field: str, value: bool, channel: str = "whatsapp"
    ) -> ConsentLog:
        """Logs teacher consent decision in consent_log."""
        entry = ConsentLog(
            id=uuid4(),
            teacher_id=teacher_id,
            field=field,
            value=value,
            channel=channel,
            created_at=datetime.now(UTC),
        )
        self.session.add(entry)
        await self.session.commit()
        return entry

    async def record_adoption_evidence(
        self,
        teacher_id: UUID,
        move_id: str,
        level: int,
        source: str,
        detail: dict[str, Any] | None = None,
    ) -> AdoptionEvidence:
        """Records an adoption evidence entry (spec/03 §3.2, spec/08 §8.2)."""
        ev = AdoptionEvidence(
            id=uuid4(),
            teacher_id=teacher_id,
            move_id=move_id,
            level=level,
            source=source,
            detail=detail or {},
            created_at=datetime.now(UTC),
        )
        self.session.add(ev)
        await self.session.commit()
        return ev

    async def get_adoption_evidence(self, teacher_id: UUID) -> list[AdoptionEvidence]:
        """Retrieves all adoption evidence rows for teacher."""
        res = await self.session.execute(
            select(AdoptionEvidence).where(AdoptionEvidence.teacher_id == teacher_id)
        )
        return list(res.scalars().all())

    async def record_review_item(
        self, kind: str, ref_id: str, reason: str | None = None
    ) -> ReviewItem:
        """Records review item for low-confidence coach or fidelity check."""
        item = ReviewItem(
            id=uuid4(),
            kind=kind,
            ref_id=ref_id,
            reason=reason,
            status="open",
            created_at=datetime.now(UTC),
        )
        self.session.add(item)
        await self.session.commit()
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
        """Records teacher explain-it-back score."""
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
        self.session.add(score)
        await self.session.commit()
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
        """Records teacher rehearsal rubric score and coach output."""
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
        self.session.add(score)
        await self.session.commit()
        return score

    async def record_move_path(
        self, teacher_id: UUID, entries: list[MovePathEntry]
    ) -> list[MovePath]:
        """Persists personal move path sequence for teacher."""
        paths: list[MovePath] = []
        for entry in entries:
            mp = MovePath(
                teacher_id=teacher_id,
                position=entry.position,
                move_id=entry.move_id,
                reason=entry.reason,
            )
            paths.append(mp)
            self.session.add(mp)
        await self.session.commit()
        return paths

    async def replace_move_path(
        self, teacher_id: UUID, entries: list[MovePathEntry]
    ) -> list[MovePath]:
        """Replaces the teacher's whole path (used when her class choice reorders it)."""
        await self.session.execute(delete(MovePath).where(MovePath.teacher_id == teacher_id))
        await self.session.flush()
        return await self.record_move_path(teacher_id, entries)

    async def done_move_ids(self, teacher_id: UUID, min_level: int) -> set[str]:
        """Moves she has already completed with adoption evidence at `min_level` or above."""
        res = await self.session.execute(
            select(AdoptionEvidence.move_id)
            .where(AdoptionEvidence.teacher_id == teacher_id, AdoptionEvidence.level >= min_level)
            .distinct()
        )
        return {str(m) for m in res.scalars().all()}

    async def record_class_outcome(
        self, teacher_id: UUID, move_id: str, answer: str, struggle_ids: list[str]
    ) -> ClassOutcome:
        """Her own answer to "Did it help your class?" (yes / some / no)."""
        row = ClassOutcome(
            teacher_id=teacher_id, move_id=move_id, answer=answer, struggle_ids=list(struggle_ids)
        )
        self.session.add(row)
        await self.session.commit()
        return row

    async def get_move_path(self, teacher_id: UUID) -> list[MovePath]:
        """Retrieves personal move path sequence for teacher."""
        res = await self.session.execute(
            select(MovePath).where(MovePath.teacher_id == teacher_id).order_by(MovePath.position)
        )
        return list(res.scalars().all())

    async def record_realism_rating(
        self, teacher_id: UUID, rating: int, scene_id: UUID | None = None
    ) -> RealismRating:
        """Records teacher realism rating (1 to 5)."""
        rr = RealismRating(
            id=uuid4(),
            teacher_id=teacher_id,
            scene_id=scene_id,
            rating=rating,
            created_at=datetime.now(UTC),
        )
        self.session.add(rr)
        await self.session.commit()
        return rr

    async def get_module_progress(
        self, teacher_id: UUID, module_id: str | None = None
    ) -> list[ModuleProgress]:
        """The teacher's module progress rows (one module, or all)."""
        stmt = select(ModuleProgress).where(ModuleProgress.teacher_id == teacher_id)
        if module_id is not None:
            stmt = stmt.where(ModuleProgress.module_id == module_id)
        return list((await self.session.execute(stmt)).scalars().all())

    async def mark_module_step(
        self, teacher_id: UUID, module_id: str, step: str, **data: Any
    ) -> ModuleProgress:
        """Records one module step as done now (idempotent: the first completion time is kept).

        Steps: learn, diagnose (verdict=...), practise, check (passed=..., covered=[...]).
        Later steps never un-do earlier ones; a repeated step updates its details.
        """
        now = datetime.now(UTC)
        row = await self.session.get(ModuleProgress, (teacher_id, module_id))
        if row is None:
            row = ModuleProgress(teacher_id=teacher_id, module_id=module_id, updated_at=now)
            self.session.add(row)
        if step == "learn":
            row.learn_done_at = row.learn_done_at or now
        elif step == "diagnose":
            row.diagnose_done_at = row.diagnose_done_at or now
            row.diagnose_verdict = data.get("verdict") or row.diagnose_verdict
        elif step == "practise":
            row.practise_done_at = row.practise_done_at or now
        elif step == "check":
            row.check_done_at = row.check_done_at or now
            row.check_passed = bool(data.get("passed"))
            row.check_covered = list(data.get("covered") or [])
        else:
            raise ValueError(f"unknown module step: {step}")
        row.updated_at = now
        await self.session.commit()
        return row

    async def record_training_rating(
        self, teacher_id: UUID, rating: int, move_id: str | None = None
    ) -> TrainingRating:
        """Stores the 1-5 "how useful was this session" rating (comment is added afterwards)."""
        tr = TrainingRating(
            id=uuid4(),
            teacher_id=teacher_id,
            move_id=move_id,
            rating=rating,
            created_at=datetime.now(UTC),
        )
        self.session.add(tr)
        await self.session.commit()
        return tr

    async def set_training_comment(self, teacher_id: UUID, comment: str) -> None:
        """Attaches the optional one-line comment to the teacher's latest training rating."""
        res = await self.session.execute(
            select(TrainingRating)
            .where(TrainingRating.teacher_id == teacher_id)
            .order_by(TrainingRating.created_at.desc())
            .limit(1)
        )
        row = res.scalar_one_or_none()
        if row is not None:
            row.comment = comment
            await self.session.commit()

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
        """Records an answered or escalated teacher question."""
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
        self.session.add(q)
        await self.session.commit()
        return q

    async def purge_teacher_data(self, teacher_id: UUID) -> None:
        """Purges teacher data across tables on delete confirmation (§8.3 step 7)."""
        await self.session.execute(
            delete(AdoptionEvidence).where(AdoptionEvidence.teacher_id == teacher_id)
        )
        await self.session.execute(
            delete(ExplainScore).where(ExplainScore.teacher_id == teacher_id)
        )
        await self.session.execute(
            delete(RehearsalScore).where(RehearsalScore.teacher_id == teacher_id)
        )
        await self.session.execute(delete(Question).where(Question.teacher_id == teacher_id))
        await self.session.execute(delete(MovePath).where(MovePath.teacher_id == teacher_id))
        await self.session.execute(
            delete(SessionState).where(SessionState.teacher_id == teacher_id)
        )
        await self.session.execute(delete(ConsentLog).where(ConsentLog.teacher_id == teacher_id))
        await self.session.execute(
            delete(RealismRating).where(RealismRating.teacher_id == teacher_id)
        )
        await self.session.execute(
            delete(TrainingRating).where(TrainingRating.teacher_id == teacher_id)
        )
        res = await self.session.execute(select(Teacher).where(Teacher.id == teacher_id))
        teacher = res.scalar_one_or_none()
        if teacher is not None:
            teacher.name = None
            teacher.cluster_id = None
            teacher.batch_id = None
            teacher.district = None
            teacher.classes = []
            teacher.experience_band = None
            teacher.start_seen_at = None
            teacher.first_year = False
            teacher.consent_service = False
            teacher.consent_share_scores = False
            teacher.onboarding_state = "NEW"
            self.session.add(teacher)
        await self.session.commit()


__all__ = [
    "SessionRepository",
]
