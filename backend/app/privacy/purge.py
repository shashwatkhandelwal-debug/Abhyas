"""Teacher data deletion and retention purge service (spec/03 §3.3, spec/08 §8.1).

Implements the "मेरा डेटा हटाएँ" (delete my data) full purge:
Permanently deletes:
- Rehearsals (Scene, Turn, RehearsalScore, RealismRating, CalibrationLabel)
- Explain-back scores (ExplainScore)
- Adoption evidence ladder records (AdoptionEvidence)
- Session state & move path (SessionState, MovePath)
- Questions & ARP observations (Question, ARPObservation)
- Messages (Message) & template history (TemplateSend)
- Consent logs (ConsentLog)
- Contact information (TeacherContact)
- Teacher record and linked AppUser account
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models import (
    AdoptionEvidence,
    AppUser,
    ARPObservation,
    CalibrationLabel,
    ConsentLog,
    ExplainScore,
    Message,
    MovePath,
    Question,
    RealismRating,
    RehearsalScore,
    Scene,
    SessionState,
    Teacher,
    TeacherContact,
    TemplateSend,
    Turn,
)

logger = logging.getLogger("abhyas.privacy.purge")


async def purge_teacher_data(db: AsyncSession, teacher_id: uuid.UUID) -> None:
    """Purges all records associated with a teacher from the database."""
    logger.info("Purging all data for teacher %s", teacher_id)

    # 1. Calibration labels referencing teacher's scenes or explain scores
    scene_ids_stmt = select(Scene.id).where(Scene.teacher_id == teacher_id)
    scene_ids = (await db.execute(scene_ids_stmt)).scalars().all()

    escore_ids_stmt = select(ExplainScore.id).where(ExplainScore.teacher_id == teacher_id)
    escore_ids = (await db.execute(escore_ids_stmt)).scalars().all()

    conditions = []
    if scene_ids:
        conditions.append(CalibrationLabel.scene_id.in_(scene_ids))
    if escore_ids:
        conditions.append(CalibrationLabel.explain_score_id.in_(escore_ids))
    if conditions:
        await db.execute(delete(CalibrationLabel).where(or_(*conditions)))

    # 2. Rehearsal turns, scores, ratings, and scenes
    await db.execute(delete(Turn).where(Turn.teacher_id == teacher_id))
    await db.execute(delete(RehearsalScore).where(RehearsalScore.teacher_id == teacher_id))
    await db.execute(delete(RealismRating).where(RealismRating.teacher_id == teacher_id))
    await db.execute(delete(Scene).where(Scene.teacher_id == teacher_id))

    # 3. Explain-back scores
    await db.execute(delete(ExplainScore).where(ExplainScore.teacher_id == teacher_id))

    # 4. Adoption evidence & observations
    await db.execute(delete(AdoptionEvidence).where(AdoptionEvidence.teacher_id == teacher_id))
    await db.execute(delete(ARPObservation).where(ARPObservation.teacher_id == teacher_id))

    # 5. Session state & move path
    await db.execute(delete(SessionState).where(SessionState.teacher_id == teacher_id))
    await db.execute(delete(MovePath).where(MovePath.teacher_id == teacher_id))

    # 6. Questions
    await db.execute(delete(Question).where(Question.teacher_id == teacher_id))

    # 7. Messages & outbound template log
    await db.execute(delete(Message).where(Message.teacher_id == teacher_id))
    await db.execute(delete(TemplateSend).where(TemplateSend.teacher_id == teacher_id))

    # 8. Consent logs
    await db.execute(delete(ConsentLog).where(ConsentLog.teacher_id == teacher_id))

    # 9. Encrypted contact info
    await db.execute(delete(TeacherContact).where(TeacherContact.teacher_id == teacher_id))

    # 10. Linked user account
    await db.execute(delete(AppUser).where(AppUser.teacher_id == teacher_id))

    # 11. Teacher record
    await db.execute(delete(Teacher).where(Teacher.id == teacher_id))

    await db.flush()
    logger.info("Successfully purged all data for teacher %s", teacher_id)
