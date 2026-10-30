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
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.auth.passwords import hash_password
from backend.app.config import settings, v2_enabled
from backend.app.content_models import MoveCard
from backend.app.db.models import (
    AdoptionEvidence,
    AggModuleBatch,
    AppUser,
    ARPObservation,
    Batch,
    ClassCheckin,
    Cluster,
    ExplainScore,
    ModuleProgress,
    Question,
    RehearsalScore,
    ReviewItem,
    Scene,
    Teacher,
    Turn,
)
from backend.app.jobs.aggregates import compute_aggregates_for_batch
from backend.app.llm.roles.coach import fallback_coach_feedback
from backend.app.llm.roles.fidelity_checker import (
    FidelityResult,
    compose_fidelity_reply,
    fallback_fidelity,
)
from backend.app.llm.schemas import CoachResult, SceneTurn
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
            # Deterministic coach and fidelity fallbacks, never the LLM roles: a seed costs
            # nothing, gives the same scores on every run and logs no guard warnings.
            def _seed_coach(
                turns: list[SceneTurn],
                acts: list[list[TeachingAct]],
                traj: dict[str, list[ChildState]],
            ) -> CoachResult:
                return CoachResult(
                    feedback=fallback_coach_feedback(
                        move, turns, acts, traj, "ravi", 16, reason="seed_demo_cohort"
                    ),
                    needs_review=True,
                    review_reason="seed_demo_cohort",
                    used_fallback=True,
                )

            coach_res_high = _seed_coach(turns_high, acts_high, traj_high)
            coach_res_low = _seed_coach(turns_low, acts_low, traj_low)

            # Explain-it-back scripts through real check_fidelity
            transcript_high = (
                "डेमो: हासिल वाली घटाव में जब इकाई से इकाई न घटे तो दहाई का एक बंडल खोलते हैं "
                "और खुली तीलियाँ गिनकर घटाते हैं। बच्चे को सीधा उत्तर नहीं बताना है।"
            )
            transcript_partial = "डेमो: घटाव में बच्चों को तीलियों से अभ्यास कराया जाएगा।"

            def _seed_fidelity(transcript: str) -> FidelityResult:
                out = fallback_fidelity(move=move, transcript=transcript)
                return FidelityResult(
                    output=out,
                    reply_hi=compose_fidelity_reply(move, out),
                    needs_review=True,
                    review_reason="seed_demo_cohort",
                    used_fallback=True,
                )

            fid_res_high = _seed_fidelity(transcript_high)
            fid_res_partial = _seed_fidelity(transcript_partial)

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
                # Live use writes one row per action, so duplicates are possible: .first()
                ae = (await session.execute(stmt_ae)).scalars().first()
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

    # 4b. Module progress for the synthetic cohort (labelled demo on the dashboards). The three
    # shared demo logins are skipped: they are seeded by db/seed.py.
    for idx, teacher in enumerate(teachers):
        if teacher.id.int <= 3:
            continue
        if await session.get(ModuleProgress, (teacher.id, target_move_id)) is not None:
            continue
        stage = idx % 5  # 0 learn only ... 3-4 everything, check passed on every other one
        stamp = now - timedelta(days=6 - stage)
        session.add(
            ModuleProgress(
                teacher_id=teacher.id,
                module_id=target_move_id,
                learn_done_at=stamp,
                diagnose_done_at=stamp if stage >= 1 else None,
                diagnose_verdict=("correct", "partly", "wrong")[idx % 3] if stage >= 1 else None,
                practise_done_at=stamp if stage >= 2 else None,
                check_done_at=stamp if stage >= 3 else None,
                check_passed=(idx % 2 == 0) if stage >= 3 else None,
                check_covered=["kp1", "kp2"] if stage >= 3 and idx % 2 == 0 else None,
                updated_at=stamp,
            )
        )
    await session.flush()

    # 4c. A small coach review queue. Every seeded score carries the fallback coach's honest low
    # confidence, but only a handful is put in the queue: a coach opening /review sees a few
    # believable items (real rows, real confidence), not one per cohort teacher.
    await _seed_review_queue(session, teachers, now)

    # 4d. Demo class check-ins so the cluster meeting pack is not empty (demo data, see below)
    await _seed_demo_checkins(session, teachers, now)

    # 4e. Latest rehearsals behind the trainer's "Where training is not landing" (demo data)
    await _seed_training_gap_demo(session, teachers, now)
    from backend.app.db.demo_loop import seed_cohort_loop

    await seed_cohort_loop(session, teachers, now)

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


# Demo class check-ins behind the cluster meeting pack: (struggle id, teachers who report it).
# They belong to the synthetic cohort teachers only (`is_demo=True`, fictional names), never to the
# shared demo logins, and only to teachers who agreed to share, as the pack counts only those. The
# pack labels them "demo data". A re-seed (`seed_database`, what "reset demo data" means on Render)
# deletes and re-creates them; the per-login reset deletes a demo login's own check-ins.
DEMO_CHECKIN_REPORTS = (
    ("NUM_SUB_REGROUP", 14),
    ("NUM_ADD_CARRY", 11),
    ("LIT_MATRA_DROP", 4),
    ("NUM_COUNTING", 2),
)
DEMO_CHECKIN_WELL = 3  # extra "it went well" check-ins (no struggle) from other teachers


async def _seed_demo_checkins(
    session: AsyncSession, teachers: list[Teacher], now: datetime
) -> None:
    """Deterministic demo check-ins for consenting cohort teachers (idempotent: delete, re-create)."""
    from backend.app.class_profile.checkin_flow import modules
    from backend.app.class_profile.library import load_library

    lib = load_library()
    module_of = {sid: m.id for m in modules(lib) for sid in m.struggle_ids}
    pool = [
        t for t in teachers[3:] if t.is_demo and t.consent_share_scores
    ]  # not the 3 shared logins
    await session.execute(
        delete(ClassCheckin).where(ClassCheckin.teacher_id.in_([t.id for t in teachers[3:]]))
    )

    def check_id(n: int) -> uuid.UUID:
        return uuid.UUID(f"00000000-0000-0001-0008-{n:012x}")

    n = 0
    start = 0
    for sid, count in DEMO_CHECKIN_REPORTS:
        for k in range(count):
            teacher = pool[(start + k) % len(pool)]
            n += 1
            session.add(
                ClassCheckin(
                    id=check_id(n),
                    teacher_id=teacher.id,
                    module_id=module_of[sid],
                    outcome="most" if k % 3 == 0 else "some",
                    struggle_ids=[sid],
                    created_at=now - timedelta(days=1 + (n % 20), hours=n % 7),
                )
            )
        start += count // 2  # overlap: some teachers report two different difficulties
    for k in range(DEMO_CHECKIN_WELL):
        n += 1
        teacher = pool[-1 - k]
        session.add(
            ClassCheckin(
                id=check_id(n),
                teacher_id=teacher.id,
                module_id="NUM_SUB_REGROUP_BUNDLES",
                outcome="well",
                struggle_ids=[],
                created_at=now - timedelta(days=2 + k),
            )
        )
    await session.flush()


# Demo rehearsals behind the trainer's "Where training is not landing" (flag TRAINING_GAP_ENABLED).
# Synthetic cohort teachers only (`is_demo=True`), only those who agreed to share, never the three
# shared logins. Each is that teacher's LATEST rehearsal of the move (newer than the older seeded
# scene), with scripted acts and no text of a teacher or a child. The page labels them demo data.
# A re-seed deletes and re-creates them (ids below); with the flag off they are not created.
# (move, how many consenting cohort teachers rehearsed it): the last one stays under n=10 so the
# trainer sees the suppression message.
DEMO_GAP_MOVES = (
    ("NUM_SUB_REGROUP_BUNDLES", 24),
    ("NUM_ADD_CARRY_BUNDLES", 14),
    ("LIT_MATRA_BLENDING", 11),
    ("NUM_PLACE_VALUE_BUNDLES", 9),
)
_GAP_CHILDREN = ("ravi", "priya", "aman")


def _gap_scene_id(n: int) -> uuid.UUID:
    return uuid.UUID(f"00000000-0000-0001-0009-{n:012x}")


def _gap_turn_id(n: int, t: int) -> uuid.UUID:
    return uuid.UUID(f"00000000-0000-0004-0000-{n * 10 + t:012x}")


def _gap_script(k: int, literacy: bool) -> list[tuple[str, str]]:
    """(act, addressed child) for one teacher: the habits follow k so the table has a spread."""
    told = k % 10 in (0, 3, 6)
    no_ask = k % 2 == 0
    no_named = k % 5 in (0, 1)
    no_concrete = k % 5 == 2
    child = "all" if no_named else _GAP_CHILDREN[k % 3]
    practice = "phonics_sound_out" if literacy else "concrete_representation"
    return [
        ("repeat_question" if no_ask else "ask_to_explain", child),
        ("praise_effort" if (no_concrete and not literacy) else practice, child),
        ("tell_answer" if told else "contrast_answers", child),
    ]


async def _seed_training_gap_demo(
    session: AsyncSession, teachers: list[Teacher], now: datetime
) -> None:
    pool = [t for t in teachers[3:] if t.is_demo and t.consent_share_scores]
    scene_ids = [_gap_scene_id(n) for n in range(1, 200)]
    await session.execute(delete(Turn).where(Turn.scene_id.in_(scene_ids)))
    await session.execute(delete(Scene).where(Scene.id.in_(scene_ids)))
    if not v2_enabled(settings.TRAINING_GAP_ENABLED):
        await session.flush()
        return
    n = 0
    for move_id, count in DEMO_GAP_MOVES:
        literacy = move_id.startswith("LIT_")
        for k, teacher in enumerate(pool[:count]):
            n += 1
            started = now - timedelta(days=1, hours=k % 6)
            session.add(
                Scene(
                    id=_gap_scene_id(n),
                    teacher_id=teacher.id,
                    move_id=move_id,
                    week_start=now.date() - timedelta(days=now.weekday()),
                    attempt=1,
                    mode="normal",
                    engine_state={"one_on_one": False, "demo": True},
                    status="ended",
                    teacher_turns=3,
                    started_at=started,
                    ended_at=started + timedelta(minutes=8),
                )
            )
            await session.flush()  # the models define no relationship(): scene row first
            for t, (act, child) in enumerate(_gap_script(k, literacy), start=1):
                session.add(
                    Turn(
                        id=_gap_turn_id(n, t),
                        teacher_id=teacher.id,
                        scene_id=_gap_scene_id(n),
                        idx=t,
                        role="teacher",
                        transcript=None,
                        acts=[act],
                        addressed_child=child,
                        created_at=started,
                    )
                )
    await session.flush()


# Cohort positions (0-based, demo4 onwards) whose seeded scores go to the coach review queue
REVIEW_QUEUE_RESCORE_POSITIONS = (4, 9, 14, 21)
REVIEW_QUEUE_EXPLAIN_POSITION = 7
REVIEW_QUEUE_QUESTION_POSITION = 6  # demo7, cluster KNP-C01: the ARP demo login sees it too
REVIEW_QUEUE_QUESTION_TEXT = "डेमो: मेरी कक्षा में कक्षा 1 और 2 के बच्चे साथ बैठते हैं। घटाव एक साथ कैसे सिखाऊँ?"


async def _seed_review_queue(session: AsyncSession, teachers: list[Teacher], now: datetime) -> None:
    """Adds the small, deterministic set of open review items (idempotent, fixed ids)."""
    from backend.app.config import settings

    def item_id(n: int) -> uuid.UUID:
        return uuid.UUID(f"00000000-0000-0001-0007-{n:012x}")

    async def add(n: int, kind: str, ref_id: str, reason: str, age_hours: int) -> None:
        if await session.get(ReviewItem, item_id(n)) is None:
            session.add(
                ReviewItem(
                    id=item_id(n),
                    kind=kind,
                    ref_id=ref_id,
                    reason=reason,
                    status="open",
                    created_at=now - timedelta(hours=age_hours),
                )
            )

    n = 0
    for position in REVIEW_QUEUE_RESCORE_POSITIONS:
        score = await session.get(
            RehearsalScore, uuid.UUID(f"00000000-0000-0001-0005-{position + 1:012x}")
        )
        if score is None or score.confidence is None:
            continue
        n += 1
        await add(
            n,
            "rehearsal_score",
            str(score.id),
            f"Coach confidence {score.confidence:.2f} below threshold "
            f"{settings.COACH_CONFIDENCE_THRESHOLD:.2f}",
            age_hours=6 * n,
        )

    explain = await session.get(
        ExplainScore,
        uuid.UUID(f"00000000-0000-0001-0006-{REVIEW_QUEUE_EXPLAIN_POSITION + 1:012x}"),
    )
    if explain is not None and explain.confidence is not None:
        n += 1
        await add(
            n,
            "explain_score",
            str(explain.id),
            f"Fidelity confidence {explain.confidence:.2f} below threshold "
            f"{settings.FIDELITY_CONFIDENCE_THRESHOLD:.2f}",
            age_hours=6 * n,
        )

    asker = teachers[REVIEW_QUEUE_QUESTION_POSITION]
    question_id = uuid.UUID("00000000-0000-0001-0008-000000000001")
    if await session.get(Question, question_id) is None:
        session.add(
            Question(
                id=question_id,
                teacher_id=asker.id,
                text=REVIEW_QUEUE_QUESTION_TEXT,
                category="pedagogy",
                answer_hi=None,
                source_ids=[],
                confidence=0.0,
                status="escalated",
                created_at=now - timedelta(hours=3),
            )
        )
        await session.flush()
    n += 1
    await add(n, "question", str(question_id), "Question escalated: pedagogy", age_hours=3)
    await session.flush()
