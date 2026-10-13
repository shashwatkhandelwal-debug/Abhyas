"""Repository for Session, Teacher, and Evidence database persistence (spec/03, spec/08)."""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models import (
    AdoptionEvidence,
    ConsentLog,
    ExplainScore,
    InviteCode,
    MovePath,
    Question,
    RehearsalScore,
    ReviewItem,
    SessionState,
    Teacher,
)
from backend.app.sessions.path import MovePathEntry

logger = logging.getLogger("abhyas.sessions.repository")

SEED_INVITE_CODES = [
    {
        "code": "KNP-C01-B1",
        "cluster_id": "KNP-C01",
        "batch_id": "KNP-B1",
        "district": "Kanpur Nagar",
        "active": True,
    },
    {
        "code": "KNP-C01-B2",
        "cluster_id": "KNP-C01",
        "batch_id": "KNP-B2",
        "district": "Kanpur Nagar",
        "active": True,
    },
    {
        "code": "DEMO",
        "cluster_id": "DEMO-C01",
        "batch_id": "DEMO-B1",
        "district": "Kanpur Nagar",
        "active": True,
    },
]


class SessionRepository:
    """Manages database persistence for sessions, teachers, and evidence."""

    def __init__(self, session: AsyncSession | None = None) -> None:
        self.session = session
        # In-memory store backing repository for unit tests or when DB is mock
        self._teachers: dict[UUID, Teacher] = {}
        self._session_states: dict[tuple[UUID, date], SessionState] = {}
        self._evidence: list[AdoptionEvidence] = []
        self._review_items: list[ReviewItem] = []
        self._explain_scores: list[ExplainScore] = []
        self._rehearsal_scores: list[RehearsalScore] = []
        self._consent_logs: list[ConsentLog] = []
        self._questions: list[Question] = []
        self._move_paths: list[MovePath] = []
        self._invite_codes: dict[str, InviteCode] = {}

        # Pre-seed invite codes
        for seed in SEED_INVITE_CODES:
            self._invite_codes[str(seed["code"]).upper()] = InviteCode(**seed)

    async def get_or_create_teacher(self, teacher_id: UUID) -> Teacher:
        """Retrieves an existing teacher or creates an initial record."""
        if self.session is not None:
            try:
                res = await self.session.execute(select(Teacher).where(Teacher.id == teacher_id))
                teacher = res.scalar_one_or_none()
                if teacher is not None:
                    return teacher
            except Exception as exc:
                logger.warning("DB query failed in get_or_create_teacher: %s", exc)

        if teacher_id not in self._teachers:
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
            self._teachers[teacher_id] = teacher
            if self.session is not None:
                try:
                    self.session.add(teacher)
                    await self.session.commit()
                except Exception as exc:
                    logger.warning("DB insert failed in get_or_create_teacher: %s", exc)

        return self._teachers[teacher_id]

    async def save_teacher(self, teacher: Teacher) -> None:
        """Persists updated teacher attributes."""
        self._teachers[teacher.id] = teacher
        if self.session is not None:
            try:
                self.session.add(teacher)
                await self.session.commit()
            except Exception as exc:
                logger.warning("DB save failed for teacher: %s", exc)

    async def get_or_create_session_state(
        self, teacher_id: UUID, week_start: date, move_id: str
    ) -> SessionState:
        """Retrieves or creates weekly SessionState."""
        key = (teacher_id, week_start)
        if self.session is not None:
            try:
                res = await self.session.execute(
                    select(SessionState).where(
                        SessionState.teacher_id == teacher_id,
                        SessionState.week_start == week_start,
                    )
                )
                state = res.scalar_one_or_none()
                if state is not None:
                    return state
            except Exception as exc:
                logger.warning("DB query failed in get_or_create_session_state: %s", exc)

        if key not in self._session_states:
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
            self._session_states[key] = st
            if self.session is not None:
                try:
                    self.session.add(st)
                    await self.session.commit()
                except Exception as exc:
                    logger.warning("DB insert failed for session_state: %s", exc)

        return self._session_states[key]

    async def save_session_state(self, session_state: SessionState) -> None:
        """Persists updated session_state."""
        key = (session_state.teacher_id, session_state.week_start)
        session_state.updated_at = datetime.now(UTC)
        self._session_states[key] = session_state
        if self.session is not None:
            try:
                self.session.add(session_state)
                await self.session.commit()
            except Exception as exc:
                logger.warning("DB save failed for session_state: %s", exc)

    async def get_invite_code(self, code: str) -> InviteCode | None:
        """Looks up an invite code (case-insensitive)."""
        norm_code = code.strip().upper()
        if self.session is not None:
            try:
                res = await self.session.execute(
                    select(InviteCode).where(
                        InviteCode.code == norm_code, InviteCode.active.is_(True)
                    )
                )
                inv = res.scalar_one_or_none()
                if inv is not None:
                    return inv
            except Exception as exc:
                logger.warning("DB query failed for invite_code: %s", exc)

        return self._invite_codes.get(norm_code)

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
        self._consent_logs.append(entry)
        if self.session is not None:
            try:
                self.session.add(entry)
                await self.session.commit()
            except Exception as exc:
                logger.warning("DB insert failed for consent_log: %s", exc)
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
        self._evidence.append(ev)
        if self.session is not None:
            try:
                self.session.add(ev)
                await self.session.commit()
            except Exception as exc:
                logger.warning("DB insert failed for adoption_evidence: %s", exc)
        return ev

    async def get_adoption_evidence(self, teacher_id: UUID) -> list[AdoptionEvidence]:
        """Retrieves all adoption evidence rows for teacher."""
        if self.session is not None:
            try:
                res = await self.session.execute(
                    select(AdoptionEvidence).where(AdoptionEvidence.teacher_id == teacher_id)
                )
                items = list(res.scalars().all())
                if items:
                    return items
            except Exception as exc:
                logger.warning("DB query failed for adoption_evidence: %s", exc)

        return [e for e in self._evidence if e.teacher_id == teacher_id]

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
        self._review_items.append(item)
        if self.session is not None:
            try:
                self.session.add(item)
                await self.session.commit()
            except Exception as exc:
                logger.warning("DB insert failed for review_item: %s", exc)
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
        self._explain_scores.append(score)
        if self.session is not None:
            try:
                self.session.add(score)
                await self.session.commit()
            except Exception as exc:
                logger.warning("DB insert failed for explain_score: %s", exc)
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
        self._rehearsal_scores.append(score)
        if self.session is not None:
            try:
                self.session.add(score)
                await self.session.commit()
            except Exception as exc:
                logger.warning("DB insert failed for rehearsal_score: %s", exc)
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
            self._move_paths.append(mp)
            if self.session is not None:
                try:
                    self.session.add(mp)
                except Exception as exc:
                    logger.warning("DB add failed for move_path: %s", exc)
        if self.session is not None:
            try:
                await self.session.commit()
            except Exception as exc:
                logger.warning("DB commit failed for move_path: %s", exc)
        return paths

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
        self._questions.append(q)
        if self.session is not None:
            try:
                self.session.add(q)
                await self.session.commit()
            except Exception as exc:
                logger.warning("DB insert failed for question: %s", exc)
        return q

    async def purge_teacher_data(self, teacher_id: UUID) -> None:
        """Purges teacher data across tables on delete confirmation (§8.3 step 7)."""
        # In-memory purge
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
        keys_to_del = [k for k in self._session_states if k[0] == teacher_id]
        for k in keys_to_del:
            del self._session_states[k]

        if self.session is not None:
            try:
                await self.session.execute(
                    delete(AdoptionEvidence).where(AdoptionEvidence.teacher_id == teacher_id)
                )
                await self.session.execute(
                    delete(ExplainScore).where(ExplainScore.teacher_id == teacher_id)
                )
                await self.session.execute(
                    delete(RehearsalScore).where(RehearsalScore.teacher_id == teacher_id)
                )
                await self.session.execute(
                    delete(Question).where(Question.teacher_id == teacher_id)
                )
                await self.session.execute(
                    delete(MovePath).where(MovePath.teacher_id == teacher_id)
                )
                await self.session.execute(
                    delete(SessionState).where(SessionState.teacher_id == teacher_id)
                )
                await self.session.execute(
                    delete(ConsentLog).where(ConsentLog.teacher_id == teacher_id)
                )
                await self.session.commit()
            except Exception as exc:
                logger.warning("DB purge failed for teacher %s: %s", teacher_id, exc)


__all__ = [
    "SessionRepository",
    "SEED_INVITE_CODES",
]
