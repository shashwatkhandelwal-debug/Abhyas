"""Labelled demo history for the two last adds: "My progress" and "what worked for other teachers".

Only exists with `settings.DEMO_MODE` on (callers from `demo_loop`), and only for demo accounts:

* demo2 and demo3 get ended rehearsals (a scene, her tagged turns, a score row) dated relative to
  "now", so "My progress" shows a trend: demo2 four group rehearsals of the regrouping move that move
  from telling the answer to asking how or why and using bundles; demo3 three of the same move. The
  rows use ids outside the cohort prefixes, so a demo reset removes whatever a session adds and
  `seed_login_loop` re-creates exactly these rows.
* the synthetic cohort gets "worked" follow-up answers on the regrouping struggle from enough distinct
  consenting teachers (`PEER_WORKED_TEACHERS`, above the suppression limit) inside the last 60 days.

Nothing here is read by an ARP, trainer or coach page for "My progress" (it is her own message).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.class_profile.followup import next_school_day
from backend.app.db.models import (
    ClassCheckin,
    ClassFollowup,
    ClassFollowupOutcome,
    RehearsalScore,
    Scene,
    Teacher,
    Turn,
)

IST = ZoneInfo("Asia/Kolkata")
STRUGGLE = "NUM_SUB_REGROUP"
MODULE = "NUM_SUB_REGROUP_BUNDLES"
PEER_WORKED_TEACHERS = 11  # cohort teachers with a "worked" answer on the regrouping struggle

CHECKIN_KIND, FOLLOWUP_KIND, OUTCOME_KIND = 0x0008, 0x0009, 0x000A
HIST_SCENE_KIND, HIST_SCORE_KIND = 0x000C, 0x000D  # not the 0004 / 0005 prefixes: reset removes them
PEER_N0 = 0xE00000
# Dated this far back (plus k days): inside the 60-day peer window but OUTSIDE the 30-day windows of
# the cluster pack and "reported vs observed", so the numbers those cards show do not move
PEER_DAYS_BACK = 35

_Turn = tuple[str, list[str], str]  # her words, tagged acts, addressed child
_Row = tuple[int, list[_Turn], int]  # days ago, her turns, rubric level of the score row

DEMO2_HISTORY: list[_Row] = [
    (
        10,
        [
            ("बच्चों, 52 में से 17 घटाओ, जवाब 35 होता है, लिखो।", ["tell_answer"], "all"),
            ("फिर से घटाओ, 52 में से 17।", ["repeat_question"], "all"),
        ],
        0,
    ),
    (
        7,
        [
            ("प्रिया, 52 में से 17 कैसे घटाया?", ["ask_to_explain"], "priya"),
            ("सही है, जवाब 35 है।", ["tell_answer"], "priya"),
        ],
        1,
    ),
    (
        4,
        [
            ("आमन, तुमने कैसे सोचा?", ["ask_to_explain"], "aman"),
            ("चलो तीलियों के बंडल से दिखाओ।", ["concrete_representation"], "all"),
        ],
        1,
    ),
    (
        1,
        [
            ("बच्चों, तीलियों का बंडल खोलकर दिखाओ, 52 में से 17।", ["concrete_representation"], "all"),
            ("तुमने यह कैसे किया, बंडल क्यों खोला?", ["ask_to_explain"], "all"),
        ],
        2,
    ),
]
DEMO3_HISTORY: list[_Row] = [
    (
        9,
        [
            ("जवाब 35 है, लिखो।", ["tell_answer"], "all"),
            ("एक और सवाल, 61 में से 28।", ["give_new_problem"], "all"),
        ],
        0,
    ),
    (
        5,
        [
            ("रवि, 61 में से 28 कैसे घटाओगे?", ["ask_to_explain"], "ravi"),
            ("बंडल खोलकर दिखाओ।", ["concrete_representation"], "ravi"),
        ],
        1,
    ),
    (
        3,
        [
            ("प्रिया, बंडल क्यों खोला, बताओ।", ["ask_to_explain"], "priya"),
            ("तीलियाँ गिनकर दिखाओ।", ["concrete_representation"], "priya"),
        ],
        2,
    ),
]


def _id(kind: int, n: int) -> uuid.UUID:
    return uuid.UUID(f"00000000-0000-0001-{kind:04x}-{n:012x}")


def _ist_day(moment: datetime) -> date:
    return moment.astimezone(IST).date()


async def seed_rehearsal_history(
    session: AsyncSession, teacher_id: uuid.UUID, now: datetime, *, is_two: bool, n: int
) -> None:
    """Ended demo rehearsals for demo2 (`is_two`) or demo3, replacing any earlier copy."""
    from backend.app.rehearsal.scene_runner import load_move_card

    history = DEMO2_HISTORY if is_two else DEMO3_HISTORY
    criteria = load_move_card(MODULE).rubric.criteria
    for k, (days_ago, turns, level) in enumerate(history, 1):
        scene_id = _id(HIST_SCENE_KIND, n * 16 + k)
        score_id = _id(HIST_SCORE_KIND, n * 16 + k)
        when = now - timedelta(days=days_ago)
        await session.execute(delete(RehearsalScore).where(RehearsalScore.id == score_id))
        await session.execute(delete(Turn).where(Turn.scene_id == scene_id))
        await session.execute(delete(Scene).where(Scene.id == scene_id))
        session.add(
            Scene(
                id=scene_id,
                teacher_id=teacher_id,
                move_id=MODULE,
                attempt=k,
                mode="normal",
                engine_state={"one_on_one": False, "status": "completed", "demo": True},
                status="ended",
                end_reason="teacher_stop",
                teacher_turns=len(turns),
                started_at=when,
                ended_at=when + timedelta(minutes=6),
            )
        )
        await session.flush()
        for i, (text, acts, child) in enumerate(turns, 1):
            session.add(
                Turn(
                    id=uuid.uuid5(scene_id, f"turn-{i}"),
                    teacher_id=teacher_id,
                    scene_id=scene_id,
                    idx=i,
                    role="teacher",
                    transcript=text,
                    acts=acts,
                    addressed_child=child,
                    stage_ms={},
                    created_at=when + timedelta(minutes=i),
                )
            )
        session.add(
            RehearsalScore(
                id=score_id,
                teacher_id=teacher_id,
                scene_id=scene_id,
                move_id=MODULE,
                attempt=k,
                scores={c.id: level for c in criteria},
                evidence={"demo": True},
                strength_hi=None,
                change_hi=None,
                exact_words_hi=None,
                confidence=1.0,
                needs_review=False,
                prompt_version="demo",
                model="demo",
                created_at=when + timedelta(minutes=7),
            )
        )
        await session.flush()


async def seed_peer_worked(session: AsyncSession, teachers: list[Teacher], now: datetime) -> None:
    """A "worked" answer on the regrouping struggle from `PEER_WORKED_TEACHERS` consenting cohort teachers.

    Teachers who already answered "worked" on it count towards the total; the others get one labelled
    demo check-in, follow-up and answer each (deterministic ids, so a re-seed replaces them). The rows
    are dated 36 to 46 days back (`PEER_DAYS_BACK`), so the 30-day trainer cards are unchanged.
    """
    consenting = [t for t in teachers[3:] if t.consent_share_scores]
    ids = [t.id for t in consenting]
    await session.execute(
        delete(ClassCheckin).where(
            ClassCheckin.id.in_([_id(CHECKIN_KIND, PEER_N0 + k) for k in range(1, len(ids) + 1)])
        )
    )
    await session.flush()
    already = set(
        (
            await session.execute(
                select(ClassFollowupOutcome.teacher_id)
                .join(ClassFollowup, ClassFollowup.id == ClassFollowupOutcome.followup_id)
                .where(
                    ClassFollowup.struggle_id == STRUGGLE,
                    ClassFollowupOutcome.outcome == "worked",
                    ClassFollowupOutcome.teacher_id.in_(ids),
                    ClassFollowupOutcome.created_at >= now - timedelta(days=60),
                )
            )
        )
        .scalars()
        .all()
    )
    todo = [t for t in consenting if t.id not in already][
        : max(0, PEER_WORKED_TEACHERS - len(already))
    ]
    for k, teacher in enumerate(todo, 1):
        n = PEER_N0 + k
        at = now - timedelta(days=PEER_DAYS_BACK + k)
        session.add(
            ClassCheckin(
                id=_id(CHECKIN_KIND, n),
                teacher_id=teacher.id,
                module_id=MODULE,
                outcome="some",
                struggle_ids=[STRUGGLE],
                created_at=at,
            )
        )
        await session.flush()
        session.add(
            ClassFollowup(
                id=_id(FOLLOWUP_KIND, n),
                teacher_id=teacher.id,
                checkin_id=_id(CHECKIN_KIND, n),
                struggle_id=STRUGGLE,
                due_date=next_school_day(_ist_day(at)),
                offered_at=at + timedelta(days=1),
                is_demo=True,
                created_at=at,
            )
        )
        await session.flush()
        session.add(
            ClassFollowupOutcome(
                id=_id(OUTCOME_KIND, n),
                teacher_id=teacher.id,
                followup_id=_id(FOLLOWUP_KIND, n),
                outcome="worked",
                created_at=at + timedelta(days=1, hours=2),
            )
        )
    await session.flush()


__all__ = ["PEER_WORKED_TEACHERS", "seed_peer_worked", "seed_rehearsal_history"]
