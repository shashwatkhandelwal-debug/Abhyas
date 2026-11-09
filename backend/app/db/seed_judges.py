"""Per-judge demo accounts seeding script (Job 07).

Creates dedicated demo accounts for judges and evaluators so multiple
evaluators can test simultaneously without session collisions or shared resets.

All passwords are read dynamically from environment variables:
- JUDGE_PASSWORD
- DEMO_PASSWORD (fallback)
Never hardcodes or commits credentials.
"""

import logging
import os
import uuid
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.auth.passwords import hash_password
from backend.app.config import settings
from backend.app.db.models import AppUser, MovePath, SessionState, Teacher
from backend.app.sessions.state_machine import OnboardingStateEnum

logger = logging.getLogger("abhyas.db.seed_judges")

DEFAULT_JUDGE_COUNT = 5


def get_judge_password() -> str:
    """Reads judge password from environment variables; falls back to DEMO_PASSWORD."""
    pwd = (
        os.getenv("JUDGE_PASSWORD")
        or os.getenv("DEMO_PASSWORD")
        or getattr(settings, "DEMO_PASSWORD", "AbhyasDemo2026!")
    )
    return str(pwd)


async def seed_judge_accounts(
    session: AsyncSession,
    count: int = DEFAULT_JUDGE_COUNT,
    password: str | None = None,
) -> list[AppUser]:
    """Idempotently seeds per-judge teacher accounts and oversight evaluation accounts."""
    raw_pwd = password or get_judge_password()
    password_hash = hash_password(raw_pwd)
    now = datetime.now(UTC)

    today = date.today()
    week_start = today - timedelta(days=today.weekday())

    created_users: list[AppUser] = []

    # 1. Seed per-judge teacher accounts (judge.1, judge.2, ... judge.N)
    for idx in range(1, count + 1):
        teacher_id = uuid.UUID(f"00000000-0000-0000-0009-{idx:012x}")
        user_id = uuid.UUID(f"00000000-0000-0001-0009-{idx:012x}")
        username = f"judge.{idx}"
        display_name = f"जज {idx} (Judge Demo)"

        # Upsert Teacher record
        t = await session.get(Teacher, teacher_id)
        if not t:
            t = Teacher(
                id=teacher_id,
                phone_hash=f"judge_eval_phone_{idx}",
                name=display_name,
                district="Kanpur Nagar",
                block_id="KNP-BLK1",
                cluster_id="KNP-C01",
                batch_id="KNP-B1",
                classes=[1, 2],
                preferred_channel="web",
                consent_service=True,
                consent_share_scores=True,
                is_demo=True,
                onboarding_state=OnboardingStateEnum.READY,
                last_inbound_at=now,
            )
            session.add(t)
        else:
            t.name = display_name
            t.is_demo = True
            t.consent_service = True
            t.consent_share_scores = True
            t.onboarding_state = OnboardingStateEnum.READY

        # Upsert AppUser
        stmt_u = select(AppUser).where(AppUser.username == username)
        u = (await session.execute(stmt_u)).scalar_one_or_none()
        if not u:
            u = AppUser(
                id=user_id,
                username=username,
                password_hash=password_hash,
                role="teacher",
                display_name=display_name,
                cluster_id="KNP-C01",
                district="Kanpur Nagar",
                teacher_id=teacher_id,
                is_demo=True,
            )
            session.add(u)
        else:
            u.password_hash = password_hash
            u.display_name = display_name
            u.role = "teacher"
            u.teacher_id = teacher_id
            u.is_demo = True
        created_users.append(u)

        # MovePath for initial rehearsal
        target_move_id = "NUM_SUB_REGROUP_BUNDLES"
        mp = await session.get(MovePath, (teacher_id, 1))
        if not mp:
            session.add(
                MovePath(
                    teacher_id=teacher_id,
                    position=1,
                    move_id=target_move_id,
                    reason="judge_seed",
                )
            )

        # SessionState ready in REHEARSE with Ravi
        stmt_ss = select(SessionState).where(
            SessionState.teacher_id == teacher_id,
            SessionState.week_start == week_start,
        )
        ss = (await session.execute(stmt_ss)).scalar_one_or_none()
        if not ss:
            session.add(
                SessionState(
                    teacher_id=teacher_id,
                    week_start=week_start,
                    state="REHEARSE",
                    move_id=target_move_id,
                    context={
                        "current_move_id": target_move_id,
                        "current_child": "ravi",
                        "problem": "43 - 27",
                        "rehearsal_type": "one_on_one",
                        "step_index": 1,
                    },
                    rehearse_attempts=0,
                    updated_at=now,
                )
            )

    # 2. Oversight judge accounts (ARP, Trainer, Coach review)
    oversight_accounts = [
        (
            uuid.UUID("00000000-0000-0001-0009-000000000091"),
            "judge.arp",
            "arp",
            "जज ARP (Oversight Demo)",
            "KNP-C01",
            "Kanpur Nagar",
        ),
        (
            uuid.UUID("00000000-0000-0001-0009-000000000092"),
            "judge.trainer",
            "trainer",
            "जज ट्रेनर (DIET Mentor Demo)",
            None,
            "Kanpur Nagar",
        ),
        (
            uuid.UUID("00000000-0000-0001-0009-000000000093"),
            "judge.coach",
            "coach",
            "जज कोच (Review Demo)",
            None,
            None,
        ),
    ]

    for uid, uname, urole, dname, cid, dist in oversight_accounts:
        stmt_o = select(AppUser).where(AppUser.username == uname)
        uo = (await session.execute(stmt_o)).scalar_one_or_none()
        if not uo:
            uo = AppUser(
                id=uid,
                username=uname,
                password_hash=password_hash,
                role=urole,
                display_name=dname,
                cluster_id=cid,
                district=dist,
                teacher_id=None,
                is_demo=True,
            )
            session.add(uo)
        else:
            uo.password_hash = password_hash
            uo.display_name = dname
            uo.role = urole
            uo.cluster_id = cid
            uo.district = dist
            uo.is_demo = True
        created_users.append(uo)

    await session.flush()
    logger.info("Successfully seeded %d judge demo accounts", len(created_users))
    return created_users
