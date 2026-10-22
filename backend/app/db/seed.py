"""Database seeding script for Abhyas (spec/03 §3.5).

Seeds:
1. Clusters and Batches (Kanpur Nagar)
2. Demo users:
   - teacher.demo1 (fresh/NEW)
   - teacher.demo2 (mid-week in REHEARSE)
   - teacher.demo3 (completed 3 moves)
   - arp.demo (cluster KNP-C01)
   - trainer.demo (district Kanpur Nagar)
   - coach.demo
3. Real admin account (username: admin, uses ADMIN_PASSWORD from env)
4. Synthetic demo cohort (db/demo_data.py)
"""

import asyncio
import logging
import uuid
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.auth.passwords import hash_password
from backend.app.config import settings
from backend.app.db.demo_data import (
    FICTIONAL_TEACHER_NAMES,
    populate_demo_cohort,
    repair_onboarding_state,
)
from backend.app.db.models import (
    AdoptionEvidence,
    AppUser,
    Batch,
    Cluster,
    ConsentLog,
    ExplainScore,
    InviteCode,
    Message,
    MovePath,
    Question,
    RealismRating,
    RehearsalScore,
    ReviewItem,
    Scene,
    SessionState,
    Teacher,
    Turn,
)
from backend.app.db.session import async_session_factory
from backend.app.retrieval.ingest import load_chunks_to_db
from backend.app.sessions.state_machine import OnboardingStateEnum

logger = logging.getLogger("abhyas.db.seed")

# Deterministic UUIDs for demo records to guarantee idempotency
TEACHER_DEMO1_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
TEACHER_DEMO2_ID = uuid.UUID("00000000-0000-0000-0000-000000000002")
TEACHER_DEMO3_ID = uuid.UUID("00000000-0000-0000-0000-000000000003")

USER_DEMO1_ID = uuid.UUID("00000000-0000-0000-0001-000000000001")
USER_DEMO2_ID = uuid.UUID("00000000-0000-0000-0001-000000000002")
USER_DEMO3_ID = uuid.UUID("00000000-0000-0000-0001-000000000003")
USER_ARP_ID = uuid.UUID("00000000-0000-0000-0001-000000000004")
USER_TRAINER_ID = uuid.UUID("00000000-0000-0000-0001-000000000005")
USER_COACH_ID = uuid.UUID("00000000-0000-0001-0000-000000000006")
USER_ADMIN_ID = uuid.UUID("00000000-0000-0001-0000-000000000007")


# The three shared demo teacher logins that are reset on logout (judges share them).
# login -> (teacher id, 1-based position in demo_data's cohort list, used for the name).
DEMO_TEACHER_LOGINS: dict[str, tuple[uuid.UUID, int]] = {
    "teacher.demo1": (TEACHER_DEMO1_ID, 1),
    "teacher.demo2": (TEACHER_DEMO2_ID, 2),
    "teacher.demo3": (TEACHER_DEMO3_ID, 3),
}

# Seed fields of the demo teachers that a chat/onboarding session can change.
# login -> (onboarding_state, classes, consent_share_scores)
_DEMO_TEACHER_PROFILE: dict[str, tuple[OnboardingStateEnum, list[int], bool]] = {
    "teacher.demo1": (OnboardingStateEnum.NEW, [1, 2], True),
    "teacher.demo2": (OnboardingStateEnum.READY, [2, 3], True),
    "teacher.demo3": (OnboardingStateEnum.READY, [1, 2, 3], False),
}

# demo3's seeded completed moves: (move_id, adoption level, evidence source)
_DEMO3_COMPLETED_MOVES: list[tuple[str, int, str]] = [
    ("NUM_SUB_REGROUP_BUNDLES", 5, "child_check"),
    ("NUM_ADD_CARRY_BUNDLES", 4, "arp_observation"),
    ("NUM_PLACE_VALUE_BUNDLES", 3, "peer_checklist"),
]

# Move ids written by older seeds that have no card in content/moves -> the real card
LEGACY_SEED_MOVE_IDS: dict[str, str] = {
    "m_sub_regroup_intro": "NUM_SUB_REGROUP_BUNDLES",
    "m_count_forward_10": "NUM_ADD_CARRY_BUNDLES",
    "m_place_value_bundling": "NUM_PLACE_VALUE_BUNDLES",
}


async def _repair_legacy_move_ids(session: AsyncSession) -> None:
    """Rewrites legacy seed move ids on the demo teachers' session/path/evidence rows."""
    demo_ids = [TEACHER_DEMO1_ID, TEACHER_DEMO2_ID, TEACHER_DEMO3_ID]
    legacy_ids = list(LEGACY_SEED_MOVE_IDS)
    repaired = 0

    for path_row in (
        (
            await session.execute(
                select(MovePath).where(
                    MovePath.teacher_id.in_(demo_ids), MovePath.move_id.in_(legacy_ids)
                )
            )
        )
        .scalars()
        .all()
    ):
        assert path_row.move_id is not None
        path_row.move_id = LEGACY_SEED_MOVE_IDS[path_row.move_id]
        repaired += 1

    for evidence in (
        (
            await session.execute(
                select(AdoptionEvidence).where(
                    AdoptionEvidence.teacher_id.in_(demo_ids),
                    AdoptionEvidence.move_id.in_(legacy_ids),
                )
            )
        )
        .scalars()
        .all()
    ):
        evidence.move_id = LEGACY_SEED_MOVE_IDS[evidence.move_id]
        repaired += 1

    for state in (
        (await session.execute(select(SessionState).where(SessionState.teacher_id.in_(demo_ids))))
        .scalars()
        .all()
    ):
        changed = False
        if state.move_id in LEGACY_SEED_MOVE_IDS:
            state.move_id = LEGACY_SEED_MOVE_IDS[state.move_id]
            changed = True
        context = dict(state.context or {})
        if context.get("current_move_id") in LEGACY_SEED_MOVE_IDS:
            context["current_move_id"] = LEGACY_SEED_MOVE_IDS[context["current_move_id"]]
            state.context = context
            changed = True
        repaired += int(changed)

    if repaired:
        logger.info("Repaired %d demo rows with legacy move ids", repaired)
        await session.flush()


async def _seed_demo2_session_state(session: AsyncSession) -> None:
    """demo2 starts the current week in REHEARSE (attempt 1)."""
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    if await session.get(SessionState, (TEACHER_DEMO2_ID, week_start)):
        return
    session.add(
        SessionState(
            teacher_id=TEACHER_DEMO2_ID,
            week_start=week_start,
            move_id="NUM_SUB_REGROUP_BUNDLES",
            state="REHEARSE",
            prior_state="MODEL",
            rehearse_attempts=1,
            context={"current_move_id": "NUM_SUB_REGROUP_BUNDLES", "current_state": "REHEARSE"},
        )
    )


async def reset_demo_teacher(session: AsyncSession, login: str) -> bool:
    """Restores one shared demo teacher to the seeded state; False for any non-demo login.

    Deletes the chat history and everything a session wrote (scenes, turns, scores, questions,
    ratings, fresh evidence), then restores profile, onboarding, week state and move path as
    seed_database creates them. Seeded cohort rows (deterministic ids) are kept so the ARP and
    trainer aggregates do not move. Does not commit: the caller owns the transaction.
    """
    entry = DEMO_TEACHER_LOGINS.get(login)
    if entry is None:
        return False
    teacher_id, position = entry
    onboarding, classes, share_scores = _DEMO_TEACHER_PROFILE[login]
    now = datetime.now(UTC)
    cutoff = now - timedelta(hours=settings.DEMO_RESET_SEED_MIN_AGE_HOURS)

    await session.execute(delete(Message).where(Message.teacher_id == teacher_id))
    await session.execute(delete(SessionState).where(SessionState.teacher_id == teacher_id))
    await session.execute(delete(MovePath).where(MovePath.teacher_id == teacher_id))
    await session.execute(delete(Question).where(Question.teacher_id == teacher_id))
    await session.execute(delete(RealismRating).where(RealismRating.teacher_id == teacher_id))
    await session.execute(
        delete(ConsentLog).where(
            ConsentLog.teacher_id == teacher_id, ConsentLog.created_at > cutoff
        )
    )
    # Evidence seeded at install time is older than the cutoff; ARP-written rows are left alone.
    await session.execute(
        delete(AdoptionEvidence).where(
            AdoptionEvidence.teacher_id == teacher_id,
            AdoptionEvidence.created_at > cutoff,
            AdoptionEvidence.source != "arp_observation",
        )
    )

    # Seeded cohort rows have deterministic ids with these prefixes (db/demo_data.py)
    stale_refs: list[str] = []
    rehearsal_scores = (
        (
            await session.execute(
                select(RehearsalScore).where(RehearsalScore.teacher_id == teacher_id)
            )
        )
        .scalars()
        .all()
    )
    for rs in rehearsal_scores:
        if not str(rs.id).startswith("00000000-0000-0001-0005-"):
            stale_refs.append(str(rs.id))
            await session.delete(rs)
    explain_scores = (
        (await session.execute(select(ExplainScore).where(ExplainScore.teacher_id == teacher_id)))
        .scalars()
        .all()
    )
    for es in explain_scores:
        if not str(es.id).startswith("00000000-0000-0001-0006-"):
            stale_refs.append(str(es.id))
            await session.delete(es)
    if stale_refs:
        await session.execute(delete(ReviewItem).where(ReviewItem.ref_id.in_(stale_refs)))
    await session.flush()

    scenes = (
        (await session.execute(select(Scene).where(Scene.teacher_id == teacher_id))).scalars().all()
    )
    for scene in scenes:
        if not str(scene.id).startswith("00000000-0000-0001-0004-"):
            await session.execute(delete(Turn).where(Turn.scene_id == scene.id))
            await session.delete(scene)
    await session.flush()

    teacher = await session.get(Teacher, teacher_id)
    if teacher is not None:
        teacher.onboarding_state = onboarding
        teacher.name = f"डेमो {FICTIONAL_TEACHER_NAMES[position - 1]}"
        teacher.classes = list(classes)
        teacher.consent_service = True
        teacher.consent_share_scores = share_scores
        teacher.consent_class_audio = False
        teacher.consent_research = False
        teacher.address_form = "f"
        teacher.lite_mode = False
        teacher.phone_hash = None
        teacher.preferred_channel = "web"
        teacher.last_inbound_at = None if onboarding == OnboardingStateEnum.NEW else now

    if teacher_id == TEACHER_DEMO2_ID:
        await _seed_demo2_session_state(session)
    if teacher_id == TEACHER_DEMO3_ID:
        for idx, (m_id, _lvl, _src) in enumerate(_DEMO3_COMPLETED_MOVES):
            session.add(
                MovePath(
                    teacher_id=TEACHER_DEMO3_ID, position=idx + 1, move_id=m_id, reason="completed"
                )
            )
    await session.flush()
    logger.info("Reset demo teacher %s to the seeded state", login)
    return True


async def seed_database() -> None:
    logger.info("Starting database seed")
    password_hash = hash_password(settings.DEMO_PASSWORD)

    async with async_session_factory() as session:
        # 1. Clusters
        cluster = await session.get(Cluster, "KNP-C01")
        if not cluster:
            cluster = Cluster(
                id="KNP-C01",
                name="कानपुर नगर संकुल 01",
                block_id="KNP-BLK1",
                district="Kanpur Nagar",
            )
            session.add(cluster)

        # 2. Batches
        for b_id, b_name in [
            ("KNP-B1", "Kanpur Nagar Oct-2026 NIPUN Ganit B1"),
            ("KNP-B2", "Kanpur Nagar Oct-2026 NIPUN Ganit B2"),
            ("KNP-B3", "Kanpur Nagar Oct-2026 NIPUN Ganit B3 (Small)"),
        ]:
            b = await session.get(Batch, b_id)
            if not b:
                session.add(
                    Batch(
                        id=b_id,
                        name=b_name,
                        district="Kanpur Nagar",
                        block_id="KNP-BLK1",
                        module="ganit_c2",
                    )
                )

        # 3. Invite Codes
        invite_codes_data = [
            ("ABHYAS-KNP", "KNP-C01", "KNP-B1"),
            ("KNP-C01-B1", "KNP-C01", "KNP-B1"),
            ("KNP-C01-B2", "KNP-C01", "KNP-B2"),
            ("DEMO", "KNP-C01", "KNP-B1"),
        ]
        for inv_code, inv_cid, inv_bid in invite_codes_data:
            invite = await session.get(InviteCode, inv_code)
            if not invite:
                session.add(
                    InviteCode(
                        code=inv_code,
                        cluster_id=inv_cid,
                        batch_id=inv_bid,
                        district="Kanpur Nagar",
                        active=True,
                    )
                )

        await session.flush()

        # 4. Teachers for Demo Users
        # Demo 1: Fresh / NEW
        t1 = await session.get(Teacher, TEACHER_DEMO1_ID)
        if not t1:
            t1 = Teacher(
                id=TEACHER_DEMO1_ID,
                name="डेमो शिक्षिका 1 (सुमन)",
                school_id="SCH-KNP-01",
                cluster_id="KNP-C01",
                district="Kanpur Nagar",
                batch_id="KNP-B1",
                classes=[1, 2],
                preferred_channel="web",
                consent_service=True,
                consent_share_scores=True,
                is_demo=True,
                onboarding_state=OnboardingStateEnum.NEW,
            )
            session.add(t1)
        else:
            repair_onboarding_state(t1, OnboardingStateEnum.NEW)

        # Demo 2: Mid-week in REHEARSE
        t2 = await session.get(Teacher, TEACHER_DEMO2_ID)
        if not t2:
            t2 = Teacher(
                id=TEACHER_DEMO2_ID,
                name="डेमो शिक्षिका 2 (अनीता)",
                school_id="SCH-KNP-02",
                cluster_id="KNP-C01",
                district="Kanpur Nagar",
                batch_id="KNP-B1",
                classes=[2, 3],
                preferred_channel="web",
                consent_service=True,
                consent_share_scores=True,
                is_demo=True,
                onboarding_state=OnboardingStateEnum.READY,
                last_inbound_at=datetime.now(UTC),
            )
            session.add(t2)
        else:
            repair_onboarding_state(t2, OnboardingStateEnum.READY)

        # Demo 3: Completed 3 moves
        t3 = await session.get(Teacher, TEACHER_DEMO3_ID)
        if not t3:
            t3 = Teacher(
                id=TEACHER_DEMO3_ID,
                name="डेमो शिक्षिका 3 (रेखा)",
                school_id="SCH-KNP-03",
                cluster_id="KNP-C01",
                district="Kanpur Nagar",
                batch_id="KNP-B1",
                classes=[1, 2, 3],
                preferred_channel="web",
                consent_service=True,
                consent_share_scores=False,  # Demonstrates non-consenting behavior
                is_demo=True,
                onboarding_state=OnboardingStateEnum.READY,
                last_inbound_at=datetime.now(UTC),
            )
            session.add(t3)
        else:
            repair_onboarding_state(t3, OnboardingStateEnum.READY)

        await session.flush()

        # Rows written by older seeds reference move ids with no move card; map them first
        await _repair_legacy_move_ids(session)

        # 5. Session State for demo2 (in REHEARSE)
        await _seed_demo2_session_state(session)

        # 6. Completed moves and Adoption Evidence for demo3
        for idx, (m_id, lvl, src) in enumerate(_DEMO3_COMPLETED_MOVES):
            # Same key as demo_data's cohort evidence: the cohort also writes demo3 rows
            # for these real moves (other levels), so (teacher, move) alone is not unique
            stmt_ev = select(AdoptionEvidence).where(
                AdoptionEvidence.teacher_id == TEACHER_DEMO3_ID,
                AdoptionEvidence.move_id == m_id,
                AdoptionEvidence.level == lvl,
            )
            ev = (await session.execute(stmt_ev)).scalar_one_or_none()
            if not ev:
                session.add(
                    AdoptionEvidence(
                        teacher_id=TEACHER_DEMO3_ID,
                        move_id=m_id,
                        level=lvl,
                        source=src,
                        detail={"seeded": True},
                        created_at=datetime.now(UTC) - timedelta(days=(3 - idx) * 7),
                    )
                )
            mp = await session.get(MovePath, (TEACHER_DEMO3_ID, idx + 1))
            if not mp:
                session.add(
                    MovePath(
                        teacher_id=TEACHER_DEMO3_ID,
                        position=idx + 1,
                        move_id=m_id,
                        reason="completed",
                    )
                )

        # 7. Demo App Users
        demo_users_data: list[
            tuple[uuid.UUID, str, str, str | None, str | None, str | None, uuid.UUID | None]
        ] = [
            (
                USER_DEMO1_ID,
                "teacher.demo1",
                "teacher",
                "डेमो शिक्षिका 1 (सुमन)",
                "KNP-C01",
                "Kanpur Nagar",
                TEACHER_DEMO1_ID,
            ),
            (
                USER_DEMO2_ID,
                "teacher.demo2",
                "teacher",
                "डेमो शिक्षिका 2 (अनीता)",
                "KNP-C01",
                "Kanpur Nagar",
                TEACHER_DEMO2_ID,
            ),
            (
                USER_DEMO3_ID,
                "teacher.demo3",
                "teacher",
                "डेमो शिक्षिका 3 (रेखा)",
                "KNP-C01",
                "Kanpur Nagar",
                TEACHER_DEMO3_ID,
            ),
            (
                USER_ARP_ID,
                "arp.demo",
                "arp",
                "ARP रमेश कुमार",
                "KNP-C01",
                "Kanpur Nagar",
                None,
            ),
            (
                USER_TRAINER_ID,
                "trainer.demo",
                "trainer",
                "डायट मेंटर सुनीता वर्मा",
                None,
                "Kanpur Nagar",
                None,
            ),
            (
                USER_COACH_ID,
                "coach.demo",
                "coach",
                "FLN कोच राजेश",
                None,
                None,
                None,
            ),
        ]

        for u_id, uname, urole, dname, cid, dist, tid in demo_users_data:
            stmt = select(AppUser).where(AppUser.username == uname)
            existing_user = (await session.execute(stmt)).scalar_one_or_none()
            if not existing_user:
                session.add(
                    AppUser(
                        id=u_id,
                        username=uname,
                        password_hash=password_hash,
                        role=urole,
                        display_name=dname,
                        cluster_id=cid,
                        district=dist,
                        teacher_id=tid,
                        is_demo=True,
                    )
                )
            else:
                existing_user.password_hash = password_hash
                existing_user.display_name = dname
                existing_user.role = urole
                existing_user.teacher_id = tid
                existing_user.cluster_id = cid
                existing_user.district = dist

        # 8. Real Admin User (uses ADMIN_PASSWORD from env, not a demo account)
        admin_password_hash = hash_password(settings.ADMIN_PASSWORD)
        stmt_admin = select(AppUser).where(AppUser.username == "admin")
        existing_admin = (await session.execute(stmt_admin)).scalar_one_or_none()
        if not existing_admin:
            session.add(
                AppUser(
                    id=USER_ADMIN_ID,
                    username="admin",
                    password_hash=admin_password_hash,
                    role="admin",
                    display_name="व्यवस्थापक (Admin)",
                    cluster_id=None,
                    district=None,
                    teacher_id=None,
                    is_demo=False,
                )
            )
        else:
            existing_admin.password_hash = admin_password_hash
            existing_admin.display_name = "व्यवस्थापक (Admin)"
            existing_admin.role = "admin"
            existing_admin.is_demo = False

        # Clean up legacy admin.demo if it exists
        stmt_legacy = select(AppUser).where(AppUser.username == "admin.demo")
        legacy_admin = (await session.execute(stmt_legacy)).scalar_one_or_none()
        if legacy_admin:
            await session.delete(legacy_admin)

        # 9. Synthetic demo cohort (db/demo_data.py)
        await populate_demo_cohort(session)

        # 10. Document chunks into doc_chunk table (spec/10 §10.4)
        await load_chunks_to_db(session)

        await session.commit()
        logger.info(
            "Successfully seeded demo users, teachers, clusters, synthetic cohort, and doc chunks."
        )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(seed_database())
