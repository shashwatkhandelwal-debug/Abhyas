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
   - admin.demo
3. Synthetic demo cohort (db/demo_data.py)
"""

import asyncio
import logging
import uuid
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select

from backend.app.auth.passwords import hash_password
from backend.app.config import settings
from backend.app.db.models import (
    AdoptionEvidence,
    AppUser,
    Batch,
    Cluster,
    InviteCode,
    MovePath,
    SessionState,
    Teacher,
)
from backend.app.db.session import async_session_factory

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


async def seed_database() -> None:
    logger.info("Starting database seed with DEMO_PASSWORD=%s", settings.DEMO_PASSWORD)
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

        # 3. Invite Code
        invite = await session.get(InviteCode, "ABHYAS-KNP")
        if not invite:
            session.add(
                InviteCode(
                    code="ABHYAS-KNP",
                    cluster_id="KNP-C01",
                    batch_id="KNP-B1",
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
                onboarding_state="NEW",
            )
            session.add(t1)

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
                onboarding_state="COMPLETE",
                last_inbound_at=datetime.now(UTC),
            )
            session.add(t2)

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
                onboarding_state="COMPLETE",
                last_inbound_at=datetime.now(UTC),
            )
            session.add(t3)

        await session.flush()

        # 5. Session State for demo2 (in REHEARSE)
        today = date.today()
        # Monday of current week
        week_start = today - timedelta(days=today.weekday())
        s2 = await session.get(SessionState, (TEACHER_DEMO2_ID, week_start))
        if not s2:
            s2 = SessionState(
                teacher_id=TEACHER_DEMO2_ID,
                week_start=week_start,
                move_id="m_sub_regroup_intro",
                state="REHEARSE",
                prior_state="MODEL",
                rehearse_attempts=1,
                context={"current_move_id": "m_sub_regroup_intro", "current_state": "REHEARSE"},
            )
            session.add(s2)

        # 6. Completed moves and Adoption Evidence for demo3
        for idx, (m_id, lvl) in enumerate(
            [
                ("m_sub_regroup_intro", 5),
                ("m_count_forward_10", 4),
                ("m_place_value_bundling", 3),
            ]
        ):
            stmt_ev = select(AdoptionEvidence).where(
                AdoptionEvidence.teacher_id == TEACHER_DEMO3_ID,
                AdoptionEvidence.move_id == m_id,
            )
            ev = (await session.execute(stmt_ev)).scalar_one_or_none()
            if not ev:
                session.add(
                    AdoptionEvidence(
                        teacher_id=TEACHER_DEMO3_ID,
                        move_id=m_id,
                        level=lvl,
                        source="rehearsal",
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
        demo_users_data = [
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
            (
                USER_ADMIN_ID,
                "admin.demo",
                "admin",
                "व्यवस्थापक (Admin)",
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

        await session.commit()
        logger.info("Successfully seeded demo users, teachers, and clusters.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(seed_database())
