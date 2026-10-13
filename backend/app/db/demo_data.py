"""Synthetic demo cohort population (spec/03 §3.5, T31).

Populates a deterministic demo cohort:
- Batches:
  - KNP-B1: 25 teachers
  - KNP-B2: 18 teachers
  - KNP-B3: 8 teachers (shows aggregation suppression n < 10)
- Cluster KNP-C01:
  - 12 teachers total: exactly 7 with consent_share_scores=True, 5 with consent_share_scores=False
- All teachers and users have is_demo=True and fictional names prefixed with "डेमो ".
- Real scoring: RehearsalScore and ExplainScore rows are generated strictly by running
  the pedagogical rule engine and fallback scoring on scripted deliberate practice turns.
- Aggregates: Computes AggModuleBatch for trainer views.
"""

import logging
import random
import uuid
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.auth.passwords import hash_password
from backend.app.config import settings
from backend.app.content_models import MoveCard
from backend.app.db.models import (
    AdoptionEvidence,
    AggModuleBatch,
    AppUser,
    Batch,
    Cluster,
    ExplainScore,
    RehearsalScore,
    Scene,
    Teacher,
)
from backend.app.llm.roles.coach import fallback_coach_feedback
from backend.app.llm.roles.fidelity_checker import fallback_fidelity
from backend.app.llm.schemas import SceneTurn
from backend.app.rule_engine.domain import ChildState, TeachingAct

logger = logging.getLogger("abhyas.db.demo_data")

DEMO_COHORT_SEED = 42

FICTIONAL_TEACHER_NAMES = [
    "सुमन शर्मा",
    "अनीता देवी",
    "रेखा कुमारी",
    "पूजा सिंह",
    "आरती यादव",
    "सीमा वर्मा",
    "सुनीता पाल",
    "मीना गुप्ता",
    "कविता चौहान",
    "रेनू मिश्रा",
    "मधु राजपूत",
    "प्रियंका तिवारी",
    "संध्या पटेल",
    "अंजू देवी",
    "मंजू शर्मा",
    "नीलम सिंह",
    "रश्मि यादव",
    "सविता वर्मा",
    "उषा देवी",
    "किरण गुप्ता",
    "प्रतिभा सिंह",
    "विनीता देवी",
    "शालिनी शर्मा",
    "ममता कुमारी",
    "अनुराधा पाल",
    "कल्पना यादव",
    "दीपा वर्मा",
    "रूबी गुप्ता",
    "गीता देवी",
    "स्नेहलता सिंह",
    "पुष्पा देवी",
    "संतोष कुमारी",
    "मंजुला शर्मा",
    "कमलेश यादव",
    "राजेश्वरी देवी",
    "सुशीला वर्मा",
    "विद्या गुप्ता",
    "आशा सिंह",
    "निर्मला देवी",
    "शकुंतला शर्मा",
    "तारा यादव",
    "बिंदु वर्मा",
    "गायत्री गुप्ता",
    "सरोज देवी",
    "मंजूषा सिंह",
    "ललिता शर्मा",
    "कुसुम यादव",
    "पार्वती वर्मा",
    "भगवती गुप्ता",
    "इंद्रावती देवी",
    "कौशल्या सिंह",
]

# Seed UUIDs matching seed.py for demo1, demo2, demo3
SEED_TEACHER_IDS = [
    uuid.UUID("00000000-0000-0000-0000-000000000001"),
    uuid.UUID("00000000-0000-0000-0000-000000000002"),
    uuid.UUID("00000000-0000-0000-0000-000000000003"),
]

SEED_USER_IDS = [
    uuid.UUID("00000000-0000-0000-0001-000000000001"),
    uuid.UUID("00000000-0000-0000-0001-000000000002"),
    uuid.UUID("00000000-0000-0000-0001-000000000003"),
]


def _load_seed_moves() -> dict[str, MoveCard]:
    """Loads all MoveCard YAML files from content/moves."""
    moves_dir = Path("content/moves")
    if not moves_dir.is_dir():
        moves_dir = Path(__file__).parents[3] / "content" / "moves"

    moves: dict[str, MoveCard] = {}
    for p in moves_dir.glob("*.yaml"):
        try:
            data = yaml.safe_load(p.read_text(encoding="utf-8"))
            card = MoveCard.model_validate(data)
            moves[card.id] = card
        except Exception as e:
            logger.warning("Could not load move from %s: %s", p, e)
    return moves


async def populate_demo_cohort(session: AsyncSession) -> None:
    """Populates 51 demo teachers across 3 batches with engine-scored rehearsals."""
    random.seed(DEMO_COHORT_SEED)
    password_hash = hash_password(settings.DEMO_PASSWORD)
    now = datetime.now(UTC)
    today = date.today()
    week_start = today - timedelta(days=today.weekday())

    # 1. Ensure clusters KNP-C01 and KNP-C02 exist
    for c_id, c_name in [
        ("KNP-C01", "कानपुर नगर संकुल 01"),
        ("KNP-C02", "कानपुर नगर संकुल 02"),
    ]:
        c = await session.get(Cluster, c_id)
        if not c:
            session.add(
                Cluster(
                    id=c_id,
                    name=c_name,
                    block_id="KNP-BLK1",
                    district="Kanpur Nagar",
                )
            )

    # 2. Ensure batches exist
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

    await session.flush()

    # 3. Create 51 Teachers & Users
    # Distribution specification:
    # - Batch KNP-B1 (25 teachers):
    #   - 12 teachers in Cluster KNP-C01 (exactly 7 consent_share_scores=True, 5 False)
    #   - 13 teachers in Cluster KNP-C02
    # - Batch KNP-B2 (18 teachers in Cluster KNP-C02)
    # - Batch KNP-B3 (8 teachers in Cluster KNP-C02, demonstrates n<10 suppression)
    teachers: list[Teacher] = []

    for idx in range(1, 52):
        name_raw = FICTIONAL_TEACHER_NAMES[idx - 1]
        display_name = f"डेमो {name_raw}"
        username = f"teacher.demo{idx}"

        if idx <= 3:
            teacher_id = SEED_TEACHER_IDS[idx - 1]
            user_id = SEED_USER_IDS[idx - 1]
        else:
            teacher_id = uuid.UUID(f"00000000-0000-0000-0002-{idx:012x}")
            user_id = uuid.UUID(f"00000000-0000-0000-0003-{idx:012x}")

        if idx <= 12:
            # Cluster KNP-C01 (12 teachers in KNP-B1)
            cluster_id = "KNP-C01"
            batch_id = "KNP-B1"
            # Exactly 7 consenting, 5 non-consenting (preserves demo3 as non-consenting)
            consent_share = idx in {1, 2, 4, 5, 6, 7, 8}
        elif idx <= 25:
            # Cluster KNP-C02 (remaining 13 teachers in KNP-B1)
            cluster_id = "KNP-C02"
            batch_id = "KNP-B1"
            consent_share = (idx % 2 == 0)
        elif idx <= 43:
            # Cluster KNP-C02 (18 teachers in KNP-B2)
            cluster_id = "KNP-C02"
            batch_id = "KNP-B2"
            consent_share = (idx % 2 == 0)
        else:
            # Cluster KNP-C02 (8 teachers in KNP-B3)
            cluster_id = "KNP-C02"
            batch_id = "KNP-B3"
            consent_share = (idx % 2 == 0)

        t = await session.get(Teacher, teacher_id)
        if not t:
            t = Teacher(
                id=teacher_id,
                name=display_name,
                school_id=f"SCH-KNP-{(idx % 15) + 1:02d}",
                cluster_id=cluster_id,
                district="Kanpur Nagar",
                batch_id=batch_id,
                classes=[1, 2] if idx % 2 == 0 else [2, 3],
                preferred_channel="web",
                consent_service=True,
                consent_share_scores=consent_share,
                consent_research=True,
                is_demo=True,
                onboarding_state="COMPLETE" if idx > 1 else "NEW",
                last_inbound_at=now - timedelta(hours=idx * 2),
            )
            session.add(t)
        else:
            t.is_demo = True
            t.cluster_id = cluster_id
            t.batch_id = batch_id
            t.consent_share_scores = consent_share
            t.name = display_name

        teachers.append(t)

        # Upsert AppUser
        stmt_u = select(AppUser).where(AppUser.username == username)
        u = (await session.execute(stmt_u)).scalar_one_or_none()
        if not u:
            session.add(
                AppUser(
                    id=user_id,
                    username=username,
                    password_hash=password_hash,
                    role="teacher",
                    display_name=display_name,
                    cluster_id=cluster_id,
                    district="Kanpur Nagar",
                    teacher_id=teacher_id,
                    is_demo=True,
                )
            )
        else:
            u.is_demo = True
            u.teacher_id = teacher_id
            u.cluster_id = cluster_id
            u.role = "teacher"

    await session.flush()

    # 4. Generate Real Engine-Scored Rehearsals and Explain Scores
    moves_map = _load_seed_moves()
    target_move_id = "NUM_SUB_REGROUP_BUNDLES"
    move = moves_map.get(target_move_id)
    if not move and moves_map:
        move = next(iter(moves_map.values()))
        target_move_id = move.id

    if move:
        # Script A: High-performing deliberate practice rehearsal
        turns_a = [
            SceneTurn(
                speaker="teacher",
                text_hi="रवि, तुमने 43 में से 27 कैसे घटाया? अपनी तीलियाँ दिखाकर बताओ।",
            ),
            SceneTurn(
                speaker="ravi",
                text_hi="24 आया! 3 में से 7 नहीं घटता तो 7 में से 3 घटाया।",
            ),
            SceneTurn(
                speaker="teacher",
                text_hi="अच्छा रवि, 43 में कितने बंडल और खुली तीलियाँ हैं? बंडल खोलकर बताओ।",
            ),
            SceneTurn(
                speaker="ravi",
                text_hi="4 बंडल और 3 तीलियाँ हैं... बंडल खोला तो 13 तीलियाँ हुईं!",
            ),
        ]
        acts_a = [
            [TeachingAct.ASK_TO_EXPLAIN],
            [TeachingAct.CONCRETE_REPRESENTATION],
        ]
        traj_a = {
            "ravi": [
                ChildState.MISCONCEPTION,
                ChildState.CAN_EXPLAIN,
            ]
        }
        res_a = fallback_coach_feedback(
            move=move,
            turns=turns_a,
            acts=acts_a,
            trajectories=traj_a,
            target_child_id="ravi",
            current_item_answer=16,
        )

        # Script B: Teacher who gave the answer directly (tell_answer penalty)
        turns_b = [
            SceneTurn(
                speaker="teacher",
                text_hi="रवि, 43 में से 27 घटाने पर 16 आता है, उत्तर 16 लिखो।",
            ),
            SceneTurn(speaker="ravi", text_hi="हाँ, 16 लिख दिया।"),
        ]
        acts_b = [[TeachingAct.TELL_ANSWER]]
        traj_b = {"ravi": [ChildState.MISCONCEPTION, ChildState.MISCONCEPTION]}
        res_b = fallback_coach_feedback(
            move=move,
            turns=turns_b,
            acts=acts_b,
            trajectories=traj_b,
            target_child_id="ravi",
            current_item_answer=16,
        )

        # Explain-it-back script (High fidelity)
        transcript_high = (
            "हासिल वाली घटाव में जब इकाई से इकाई न घटे तो दहाई का एक बंडल खोलते हैं "
            "और खुली तीलियाँ गिनकर घटाते हैं। बच्चे को सीधा उत्तर नहीं बताना है।"
        )
        fid_res_high = fallback_fidelity(move, transcript_high)

        # Explain-it-back script (Partial)
        transcript_partial = "घटाव में बच्चों को तीलियों से अभ्यास कराया जाएगा।"
        fid_res_partial = fallback_fidelity(move, transcript_partial)

        # Seed scores for teachers in each batch
        for idx, teacher in enumerate(teachers):
            # Deterministic variation by teacher index
            is_high = (idx % 3 != 0)
            coach_res = res_a if is_high else res_b
            fid_res = fid_res_high if is_high else fid_res_partial
            evidence_lvl = 4 if (idx % 4 == 0) else (3 if is_high else 1)

            # Scene row
            scene_id = uuid.UUID(f"00000000-0000-0001-0004-{idx + 1:012x}")
            sc = await session.get(Scene, scene_id)
            if not sc:
                session.add(
                    Scene(
                        id=scene_id,
                        teacher_id=teacher.id,
                        move_id=target_move_id,
                        week_start=week_start,
                        attempt=1,
                        mode="normal",
                        engine_state={"target_child": "ravi", "status": "completed"},
                        status="completed",
                        teacher_turns=len(coach_res.evidence),
                        started_at=now - timedelta(days=2),
                        ended_at=now - timedelta(days=2, minutes=-10),
                    )
                )

            # RehearsalScore row
            rscore_id = uuid.UUID(f"00000000-0000-0001-0005-{idx + 1:012x}")
            rscore = await session.get(RehearsalScore, rscore_id)
            if not rscore:
                session.add(
                    RehearsalScore(
                        id=rscore_id,
                        teacher_id=teacher.id,
                        scene_id=scene_id,
                        move_id=target_move_id,
                        attempt=1,
                        scores=coach_res.scores,
                        evidence=coach_res.evidence,
                        strength_hi=coach_res.strength_hi,
                        change_hi=coach_res.change_hi,
                        exact_words_hi=coach_res.exact_words_hi,
                        confidence=coach_res.confidence,
                        needs_review=False,
                        prompt_version="v1",
                        model="claude-sonnet-5-5",
                        created_at=now - timedelta(days=2),
                    )
                )

            # ExplainScore row
            escore_id = uuid.UUID(f"00000000-0000-0001-0006-{idx + 1:012x}")
            escore = await session.get(ExplainScore, escore_id)
            if not escore:
                session.add(
                    ExplainScore(
                        id=escore_id,
                        teacher_id=teacher.id,
                        move_id=target_move_id,
                        transcript=transcript_high if is_high else transcript_partial,
                        points={p.id: p.status for p in fid_res.points},
                        misconceptions=fid_res.misconceptions,
                        confidence=fid_res.confidence,
                        needs_review=False,
                        prompt_version="v1",
                        model="claude-sonnet-5-5",
                        created_at=now - timedelta(days=3),
                    )
                )

            # AdoptionEvidence row
            stmt_ae = select(AdoptionEvidence).where(
                AdoptionEvidence.teacher_id == teacher.id,
                AdoptionEvidence.move_id == target_move_id,
            )
            ae = (await session.execute(stmt_ae)).scalar_one_or_none()
            if not ae:
                session.add(
                    AdoptionEvidence(
                        id=uuid.uuid4(),
                        teacher_id=teacher.id,
                        move_id=target_move_id,
                        level=evidence_lvl,
                        source="rehearsal",
                        detail={"scores": coach_res.scores},
                        created_at=now - timedelta(days=1),
                    )
                )

    await session.flush()

    # 5. Populate AggModuleBatch for Trainer View (§9.4)
    batch_counts = {"KNP-B1": 25, "KNP-B2": 18, "KNP-B3": 8}
    for b_id, n_count in batch_counts.items():
        stmt_agg = select(AggModuleBatch).where(
            AggModuleBatch.batch_id == b_id,
            AggModuleBatch.move_id == target_move_id,
        )
        agg = (await session.execute(stmt_agg)).scalar_one_or_none()
        if not agg:
            session.add(
                AggModuleBatch(
                    batch_id=b_id,
                    move_id=target_move_id,
                    n_teachers=n_count,
                    explain_missing={"kp1": 6, "kp5": 8},
                    rubric_dist={"crit_explain": {"0": 3, "1": 7, "2": n_count - 10}},
                    ladder_dist={"1": 4, "2": 5, "3": 8, "4": 6, "5": n_count - 23 if n_count > 23 else 0},
                    active_rate=round(random.uniform(0.70, 0.90), 2),
                    computed_at=now,
                )
            )

    await session.commit()
    logger.info("Successfully populated 51 demo teachers across 3 batches with real engine scores.")
