"""Synthetic demo cohort population (spec/03 §3.5, T31).

Populates a deterministic demo cohort:
- Batches:
  - KNP-B1: 25 teachers
  - KNP-B2: 18 teachers
  - KNP-B3: 8 teachers (shows aggregation suppression n < 10)
- Cluster KNP-C01:
  - 12 teachers total: exactly 7 with consent_share_scores=True, 5 with consent_share_scores=False
- All teachers and users have is_demo=True and fictional names prefixed with "डेमो ".
- Real scoring: Deliberate practice rehearsals are run using SceneRunner (MockLLM + MockTTS)
  on scripted teacher turns ONLY. Child lines and acts come entirely from the rule engine/tagger.
  Then the real coach path (coach_feedback) and fidelity checker (check_fidelity) evaluate the turns.
- Honest provenance: model="mock" or "fallback", real confidence, and needs_review as returned.
- Evidence levels strictly match source:
  level 1 -> rehearsal (>=3 teacher turns)
  level 2 -> reflection
  level 3 -> peer_checklist
  level 4 -> arp_observation (with ARPObservation record)
  level 5 -> child_check
- Aggregates: Computed directly from demo database rows using compute_aggregates_for_batch.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.auth.passwords import hash_password
from backend.app.config import settings
from backend.app.content_models import MoveCard
from backend.app.db.models import (
    AdoptionEvidence,
    AggModuleBatch,
    AppUser,
    ARPObservation,
    Batch,
    Cluster,
    ExplainScore,
    RehearsalScore,
    Scene,
    Teacher,
    Turn,
)
from backend.app.jobs.aggregates import compute_aggregates_for_batch
from backend.app.llm.roles.coach import coach_feedback
from backend.app.llm.roles.fidelity_checker import check_fidelity
from backend.app.llm.schemas import SceneTurn
from backend.app.rehearsal.scene_runner import SceneRunner
from backend.app.rehearsal.scene_store import SceneStore
from backend.app.rule_engine.domain import ChildState, TeachingAct
from backend.app.sessions.state_machine import OnboardingStateEnum
from backend.app.speech.tts import MockTTS

logger = logging.getLogger("abhyas.db.demo_data")

VALID_ONBOARDING_STATES = frozenset(state.value for state in OnboardingStateEnum)


def repair_onboarding_state(teacher: Teacher, target: OnboardingStateEnum) -> None:
    """Sets target only when the stored onboarding_state is not a valid OnboardingStateEnum value.

    Repairs rows written by older seeds (e.g. "COMPLETE") without resetting valid progress.
    """
    if teacher.onboarding_state not in VALID_ONBOARDING_STATES:
        logger.info(
            "Repairing invalid onboarding_state %r -> %s for teacher %s",
            teacher.onboarding_state,
            target.value,
            teacher.id,
        )
        teacher.onboarding_state = target


@contextmanager
def _force_mock_llm() -> Generator[None, None, None]:
    """Forces settings.LLM_PROVIDER to 'mock' locally during cohort population, restoring in finally."""
    prev = settings.LLM_PROVIDER
    settings.LLM_PROVIDER = "mock"
    try:
        yield
    finally:
        settings.LLM_PROVIDER = prev


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
        except (OSError, yaml.YAMLError, ValidationError) as e:
            logger.warning("Could not load move from %s: %s", p, e)
    return moves


async def populate_demo_cohort(session: AsyncSession) -> None:
    """Populates 51 demo teachers across 3 batches with engine-scored rehearsals.

    Note: cohort = 2 engine-run trajectories replicated, labelled demo.
    """
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
            consent_share = idx % 2 == 0
        elif idx <= 43:
            # Cluster KNP-C02 (18 teachers in KNP-B2)
            cluster_id = "KNP-C02"
            batch_id = "KNP-B2"
            consent_share = idx % 2 == 0
        else:
            # Cluster KNP-C02 (8 teachers in KNP-B3)
            cluster_id = "KNP-C02"
            batch_id = "KNP-B3"
            consent_share = idx % 2 == 0

        onboarding_target = OnboardingStateEnum.READY if idx > 1 else OnboardingStateEnum.NEW
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
                onboarding_state=onboarding_target,
                last_inbound_at=now - timedelta(hours=idx * 2),
            )
            session.add(t)
        else:
            t.is_demo = True
            t.cluster_id = cluster_id
            t.batch_id = batch_id
            t.consent_share_scores = consent_share
            t.name = display_name
            repair_onboarding_state(t, onboarding_target)

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

    # 4. Generate Real Rehearsal Scenes & Scores via SceneRunner and real Coach/Fidelity paths
    moves_map = _load_seed_moves()
    target_move_id = "NUM_SUB_REGROUP_BUNDLES"
    move = moves_map.get(target_move_id)
    if not move and moves_map:
        move = next(iter(moves_map.values()))
        target_move_id = move.id

    if move:
        with _force_mock_llm():
            # Scripted TEACHER turns only (child lines & acts generated by SceneRunner / engine)
            teacher_turns_high = [
                "रवि, तुमने कैसे घटाया? मुझे समझाओ",
                "तीलियाँ और बंडल खोलकर बताओ",
                "शाबाश, 10 का बंडल खोलो",
            ]
            teacher_turns_low = [
                "रवि, 43 में से 27 घटाओ",
                "रवि, इसका उत्तर 16 है, कॉपी में 16 लिखो",
                "चलो 16 लिख दिया",
            ]

            # Shared scene runner with MockTTS and in-memory store
            mock_tts = MockTTS()
            mem_store = SceneStore()
            runner = SceneRunner(tts_provider=mock_tts, store=mem_store)

            # Pre-generate the two distinct rehearsal trajectories through the real engine
            # Scenario High
            rec_high = await runner.create_scene(teachers[0].id, move_id=target_move_id)
            for t_text in teacher_turns_high:
                await runner.turn(rec_high.scene_id, t_text, synthesize_audio=False)
            stored_high = await mem_store.get(rec_high.scene_id)
            assert stored_high is not None, "Failed to retrieve high scene record from memory store"

            # Scenario Low
            rec_low = await runner.create_scene(teachers[1].id, move_id=target_move_id)
            for t_text in teacher_turns_low:
                await runner.turn(rec_low.scene_id, t_text, synthesize_audio=False)
            stored_low = await mem_store.get(rec_low.scene_id)
            assert stored_low is not None, "Failed to retrieve low scene record from memory store"

            # Helper to extract scene turns, acts, and child trajectories from a completed SceneRecord
            def _extract_scene_data(
                sc_record: Any,
            ) -> tuple[list[SceneTurn], list[list[TeachingAct]], dict[str, list[ChildState]]]:
                sturns: list[SceneTurn] = []
                sacts: list[list[TeachingAct]] = []
                for tr in sc_record.turns:
                    sturns.append(SceneTurn(speaker="teacher", text_hi=tr.transcript))
                    act_enums = [
                        TeachingAct(a) for a in tr.acts if a in TeachingAct._value2member_map_
                    ]
                    sacts.append(act_enums)
                    for cl in tr.child_lines:
                        sturns.append(SceneTurn(speaker=cl.persona_id, text_hi=cl.line_hi))
                straj = {
                    c.persona_id: [ChildState.MISCONCEPTION, c.state]
                    for c in sc_record.scene_state.children
                }
                return sturns, sacts, straj

            turns_high, acts_high, traj_high = _extract_scene_data(stored_high)
            turns_low, acts_low, traj_low = _extract_scene_data(stored_low)

            # Run real coach path on the engine-generated turns
            coach_res_high = await coach_feedback(
                move=move,
                turns=turns_high,
                acts=acts_high,
                trajectories=traj_high,
                target_child_id="ravi",
                current_item_answer=16,
            )
            coach_res_low = await coach_feedback(
                move=move,
                turns=turns_low,
                acts=acts_low,
                trajectories=traj_low,
                target_child_id="ravi",
                current_item_answer=16,
            )

            # Explain-it-back scripts through real check_fidelity
            transcript_high = (
                "डेमो: हासिल वाली घटाव में जब इकाई से इकाई न घटे तो दहाई का एक बंडल खोलते हैं "
                "और खुली तीलियाँ गिनकर घटाते हैं। बच्चे को सीधा उत्तर नहीं बताना है।"
            )
            transcript_partial = "डेमो: घटाव में बच्चों को तीलियों से अभ्यास कराया जाएगा।"

            fid_res_high = await check_fidelity(move, transcript_high)
            fid_res_partial = await check_fidelity(move, transcript_partial)

        # Seed rows for each demo teacher
        for idx, teacher in enumerate(teachers):
            is_high = idx % 3 != 0
            chosen_rec = stored_high if is_high else stored_low
            chosen_coach = coach_res_high if is_high else coach_res_low
            chosen_fid = fid_res_high if is_high else fid_res_partial

            # Provenance: model="fallback" if used_fallback else "mock", real confidence & needs_review
            coach_model = "fallback" if chosen_coach.used_fallback else "mock"
            fid_model = "fallback" if chosen_fid.used_fallback else "mock"

            # 1. DB Scene row
            scene_id = uuid.UUID(f"00000000-0000-0001-0004-{idx + 1:012x}")
            sc = await session.get(Scene, scene_id)
            if not sc:
                sc = Scene(
                    id=scene_id,
                    teacher_id=teacher.id,
                    move_id=target_move_id,
                    week_start=week_start,
                    attempt=1,
                    mode="normal",
                    engine_state={
                        "target_child": "ravi",
                        "status": "completed",
                        "current_item_answer": 16,
                    },
                    status="ended",  # check_scene_status allows only 'active' / 'ended'
                    teacher_turns=len(chosen_rec.turns),
                    started_at=now - timedelta(days=2),
                    ended_at=now - timedelta(days=2, minutes=-10),
                )
                session.add(sc)
                # Models define no relationship(), so the unit of work cannot order the
                # Turn / RehearsalScore inserts (FK scene_id -> scene.id) after this one.
                # Flush the scene row first.
                await session.flush()

            # 2. DB Turn rows linking to Scene
            for t_idx, t_rec in enumerate(chosen_rec.turns):
                t_user_id = uuid.UUID(f"00000000-0000-0002-0000-{(idx + 1) * 10 + t_idx:012x}")
                t_user = await session.get(Turn, t_user_id)
                if not t_user:
                    session.add(
                        Turn(
                            id=t_user_id,
                            teacher_id=teacher.id,
                            scene_id=scene_id,
                            idx=t_idx + 1,
                            role="teacher",
                            transcript=t_rec.transcript,
                            acts=t_rec.acts,
                            stage_ms=t_rec.stage_ms,
                            created_at=now - timedelta(days=2),
                        )
                    )
                for cl_idx, cl in enumerate(t_rec.child_lines):
                    t_child_id = uuid.UUID(
                        f"00000000-0000-0003-0000-{(idx + 1) * 100 + t_idx * 10 + cl_idx:012x}"
                    )
                    t_child = await session.get(Turn, t_child_id)
                    if not t_child:
                        session.add(
                            Turn(
                                id=t_child_id,
                                teacher_id=teacher.id,
                                scene_id=scene_id,
                                idx=t_idx + 1,
                                role="child",
                                addressed_child=cl.persona_id,
                                line_hi=cl.line_hi,
                                created_at=now - timedelta(days=2),
                            )
                        )

            # 3. DB RehearsalScore row with honest provenance
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
                        scores=chosen_coach.feedback.scores,
                        evidence=chosen_coach.feedback.evidence,
                        strength_hi=chosen_coach.feedback.strength_hi,
                        change_hi=chosen_coach.feedback.change_hi,
                        exact_words_hi=chosen_coach.feedback.exact_words_hi,
                        confidence=chosen_coach.feedback.confidence,
                        needs_review=chosen_coach.needs_review,
                        prompt_version="v1",
                        model=coach_model,
                        created_at=now - timedelta(days=2),
                    )
                )

            # 4. DB ExplainScore row with honest provenance
            escore_id = uuid.UUID(f"00000000-0000-0001-0006-{idx + 1:012x}")
            escore = await session.get(ExplainScore, escore_id)
            if not escore:
                session.add(
                    ExplainScore(
                        id=escore_id,
                        teacher_id=teacher.id,
                        move_id=target_move_id,
                        transcript=transcript_high if is_high else transcript_partial,
                        points={p.id: p.status for p in chosen_fid.output.points},
                        misconceptions=chosen_fid.output.misconceptions,
                        confidence=chosen_fid.output.confidence,
                        needs_review=chosen_fid.needs_review,
                        prompt_version="v1",
                        model=fid_model,
                        created_at=now - timedelta(days=3),
                    )
                )

            # 5. AdoptionEvidence matching source strictly (spec/03 §3.5)
            # Cumulative: if level N is added, all levels 1..N exist.
            max_lvl = 1
            if idx == 12:
                max_lvl = 5
            elif idx % 5 == 0:
                max_lvl = 4
            elif idx % 3 == 0:
                max_lvl = 3
            elif idx % 2 == 0:
                max_lvl = 2

            sources = {
                1: "rehearsal",
                2: "reflection",
                3: "peer_checklist",
                4: "arp_observation",
                5: "child_check",
            }
            evidence_plan: list[tuple[int, str]] = [
                (lvl, sources[lvl]) for lvl in range(1, max_lvl + 1)
            ]

            if max_lvl >= 4:
                # Add real ARPObservation row for higher levels
                arp_obs_id = uuid.UUID(f"00000000-0000-0004-0000-{(idx + 1):012x}")
                arp_obs = await session.get(ARPObservation, arp_obs_id)
                if not arp_obs:
                    session.add(
                        ARPObservation(
                            id=arp_obs_id,
                            teacher_id=teacher.id,
                            move_id=target_move_id,
                            checklist={"concrete_materials": True, "elicited_explanation": True},
                            notes="डेमो: कक्षा में तीलियों का अच्छा उपयोग देखा गया।",
                            observed_on=today - timedelta(days=5),
                            created_at=now - timedelta(days=5),
                        )
                    )

            for lvl, src in evidence_plan:
                stmt_ae = select(AdoptionEvidence).where(
                    AdoptionEvidence.teacher_id == teacher.id,
                    AdoptionEvidence.move_id == target_move_id,
                    AdoptionEvidence.level == lvl,
                )
                ae = (await session.execute(stmt_ae)).scalar_one_or_none()
                if not ae:
                    session.add(
                        AdoptionEvidence(
                            id=uuid.uuid4(),
                            teacher_id=teacher.id,
                            move_id=target_move_id,
                            level=lvl,
                            source=src,
                            detail={"scores": chosen_coach.feedback.scores},
                            created_at=now - timedelta(days=7 - lvl),
                        )
                    )

    await session.flush()

    # 5. Compute AggModuleBatch using compute_aggregates_for_batch (no hard-coded or random numbers)
    for b_id in ["KNP-B1", "KNP-B2", "KNP-B3"]:
        computed_agg = await compute_aggregates_for_batch(session, b_id, target_move_id)
        stmt_agg = select(AggModuleBatch).where(
            AggModuleBatch.batch_id == b_id,
            AggModuleBatch.move_id == target_move_id,
        )
        existing_agg = (await session.execute(stmt_agg)).scalar_one_or_none()
        if not existing_agg:
            session.add(computed_agg)
        else:
            existing_agg.n_teachers = computed_agg.n_teachers
            existing_agg.explain_missing = computed_agg.explain_missing
            existing_agg.rubric_dist = computed_agg.rubric_dist
            existing_agg.ladder_dist = computed_agg.ladder_dist
            existing_agg.active_rate = computed_agg.active_rate
            existing_agg.computed_at = computed_agg.computed_at

    await session.commit()
    logger.info(
        "Successfully populated demo cohort with SceneRunner deliberate practice rehearsals."
    )
