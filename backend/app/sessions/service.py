"""SessionService orchestrating conversation flow, state machine, and DB side effects (spec/08, T20/T21)."""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.intents import (
    BUTTON_INTENT_MAP,
    Intent,
    extract_ask_query,
    match_intent,
)
from backend.app.core.messages import get_message
from backend.app.core.types import Button, InboundMessage, OutboundMessage
from backend.app.llm.roles.coach import coach_feedback
from backend.app.llm.roles.fidelity_checker import check_fidelity
from backend.app.llm.roles.guide_answerer import answer_guide_question, compose_guide_reply
from backend.app.llm.roles.question_classifier import classify_question
from backend.app.llm.schemas import RetrievedChunk
from backend.app.rehearsal.scene_runner import SceneRunner, load_move_card
from backend.app.rehearsal.scene_store import scene_store
from backend.app.retrieval.search import GuideRetriever
from backend.app.rule_engine.domain import ChildState, SceneTurn, TeachingAct
from backend.app.sessions.path import compute_move_path
from backend.app.sessions.repository import SessionRepository
from backend.app.sessions.state_machine import (
    OnboardingStateEnum,
    OnboardingStateMachine,
    SessionContext,
    SessionStateEnum,
    WeeklyStateMachine,
)

logger = logging.getLogger("abhyas.sessions.service")


class SessionService:
    """Orchestrates deliberate practice conversation sessions, state transitions, and database side effects."""

    def __init__(
        self,
        repository: SessionRepository | None = None,
        db_session: AsyncSession | None = None,
        scene_runner: SceneRunner | None = None,
    ) -> None:
        self.repo = repository or SessionRepository(db_session)
        self.scene_runner = scene_runner or SceneRunner()
        self.retriever = GuideRetriever()
        self._contexts: dict[UUID, SessionContext] = {}

    async def get_or_create_context(self, teacher_id: UUID) -> SessionContext:
        """Loads or constructs a SessionContext from database state."""
        if teacher_id in self._contexts:
            return self._contexts[teacher_id]

        teacher = await self.repo.get_or_create_teacher(teacher_id)
        today = date.today()
        # Monday of current week
        week_start = today.fromordinal(today.toordinal() - today.weekday())

        db_session = await self.repo.get_or_create_session_state(
            teacher_id=teacher_id,
            week_start=week_start,
            move_id="NUM_PLACE_VALUE_BUNDLES",
        )

        ctx = SessionContext(
            teacher_id=str(teacher_id),
            week_start=str(week_start),
            current_move_id=db_session.move_id,
            current_state=SessionStateEnum(db_session.state),
            prior_state_before_ask=(
                SessionStateEnum(db_session.prior_state) if db_session.prior_state else None
            ),
            onboarding_state=OnboardingStateEnum(teacher.onboarding_state),
            retries_count=db_session.rehearse_attempts,
            name=teacher.name,
            address_form=teacher.address_form or "f",
            cluster_id=teacher.cluster_id,
            batch_id=teacher.batch_id,
            district=teacher.district,
            experience_band=teacher.experience_band,
            first_year=bool(teacher.first_year),
            classes=teacher.classes or [],
            consent_service=bool(teacher.consent_service),
            consent_share_scores=bool(teacher.consent_share_scores),
            lite_mode=bool(teacher.lite_mode),
            last_inbound_at=teacher.last_inbound_at,
        )
        self._contexts[teacher_id] = ctx
        return ctx

    async def _sync_context_to_db(self, ctx: SessionContext, teacher_uuid: UUID) -> None:
        """Persists SessionContext back to Teacher and SessionState records."""
        teacher = await self.repo.get_or_create_teacher(teacher_uuid)
        teacher.name = ctx.name
        teacher.address_form = ctx.address_form
        teacher.cluster_id = ctx.cluster_id
        teacher.batch_id = ctx.batch_id
        teacher.district = ctx.district
        teacher.experience_band = ctx.experience_band
        teacher.first_year = ctx.first_year
        teacher.classes = ctx.classes
        teacher.consent_service = ctx.consent_service
        teacher.consent_share_scores = ctx.consent_share_scores
        teacher.onboarding_state = ctx.onboarding_state.value
        teacher.last_inbound_at = ctx.last_inbound_at
        teacher.lite_mode = ctx.lite_mode
        await self.repo.save_teacher(teacher)

        if ctx.onboarding_state == OnboardingStateEnum.READY:
            week_d = date.fromisoformat(ctx.week_start)
            db_state = await self.repo.get_or_create_session_state(
                teacher_uuid, week_d, ctx.current_move_id
            )
            db_state.state = ctx.current_state.value
            db_state.prior_state = (
                ctx.prior_state_before_ask.value if ctx.prior_state_before_ask else None
            )
            db_state.rehearse_attempts = ctx.retries_count
            db_state.context = {
                "evidence_level": ctx.evidence_level,
                "rehearsal_turns_count": ctx.rehearsal_turns_count,
                "reflect_step": ctx.reflect_step,
                "reflection_type": ctx.reflection_type,
            }
            await self.repo.save_session_state(db_state)

    async def handle_inbound(self, inbound: InboundMessage) -> list[OutboundMessage]:
        """Dispatches an inbound teacher message through conversation flow and persists side effects."""
        teacher_id = inbound.teacher_id
        ctx = await self.get_or_create_context(teacher_id)
        now = datetime.now(UTC)
        address_form = ctx.address_form
        text_content = (inbound.text or "").strip()
        btn_id = inbound.button_id

        # Determine matched intent
        matched_intent = match_intent(
            text=text_content,
            in_rehearsal=(
                ctx.current_state == SessionStateEnum.REHEARSE
                and ctx.onboarding_state == OnboardingStateEnum.READY
            ),
            button_id=btn_id or (text_content if text_content in BUTTON_INTENT_MAP else None),
        )

        # 1. Inactivity resume rule (§8.2: > 6h inactivity in mid-week state)
        if ctx.onboarding_state == OnboardingStateEnum.READY and ctx.last_inbound_at is not None:
            diff_hours = (now - ctx.last_inbound_at).total_seconds() / 3600.0
            mid_week = ctx.current_state not in (SessionStateEnum.DONE, SessionStateEnum.LEARN)
            is_resume_click = (
                btn_id in ("btn_continue", "btn_restart") or matched_intent == Intent.NEXT
            )

            if diff_hours > 6.0 and mid_week and not is_resume_click:
                ctx.last_inbound_at = now
                await self._sync_context_to_db(ctx, teacher_id)
                state_name_hi = get_message(f"state_{ctx.current_state.value}", address_form)
                resume_text = get_message("resume_prompt", address_form, state_name=state_name_hi)
                return [
                    OutboundMessage(
                        kind="buttons",
                        text_hi=resume_text,
                        buttons=[
                            Button(
                                id="btn_continue",
                                title_hi=get_message("btn_continue", address_form),
                            ),
                            Button(
                                id="btn_restart", title_hi=get_message("btn_restart", address_form)
                            ),
                        ],
                    )
                ]

            if is_resume_click and btn_id == "btn_restart":
                ctx.current_state = SessionStateEnum.LEARN
                ctx.rehearsal_turns_count = 0
                ctx.retries_count = 0
                ctx.last_inbound_at = now
                await self._sync_context_to_db(ctx, teacher_id)
                return [
                    OutboundMessage(
                        kind="text",
                        text_hi=get_message("learn_intro", address_form),
                        buttons=[
                            Button(
                                id="btn_understood",
                                title_hi=get_message("btn_understood", address_form),
                            ),
                            Button(
                                id="btn_replay", title_hi=get_message("btn_replay", address_form)
                            ),
                        ],
                    )
                ]

        ctx.last_inbound_at = now

        # 2. Delete confirmation flow (§8.3 step 7)
        if ctx.awaiting_delete_confirm:
            if (
                matched_intent in (Intent.CONFIRM_DELETE, Intent.CONFIRM_YES)
                or btn_id == "btn_delete_confirm"
                or text_content in ("हाँ, मिटाएँ", "confirm_delete")
            ):
                ctx.awaiting_delete_confirm = False
                wsm = WeeklyStateMachine(ctx)
                wsm.reset()
                await self.repo.purge_teacher_data(teacher_id)
                await self._sync_context_to_db(ctx, teacher_id)
                return [
                    OutboundMessage(
                        kind="text",
                        text_hi=get_message("data_deleted", address_form),
                    )
                ]
            else:
                ctx.awaiting_delete_confirm = False
                target = ctx.prior_state_before_delete or SessionStateEnum.LEARN
                ctx.current_state = target
                ctx.prior_state_before_delete = None
                await self._sync_context_to_db(ctx, teacher_id)
                prompt_key = WeeklyStateMachine(ctx).get_state_prompt_key(target)
                return [
                    OutboundMessage(
                        kind="text",
                        text_hi=get_message(prompt_key, address_form),
                    )
                ]

        if matched_intent == Intent.DELETE or text_content == "delete":
            ctx.awaiting_delete_confirm = True
            ctx.prior_state_before_delete = ctx.current_state
            await self._sync_context_to_db(ctx, teacher_id)
            return [
                OutboundMessage(
                    kind="buttons",
                    text_hi=get_message("delete_confirm", address_form),
                    buttons=[
                        Button(id="btn_delete_confirm", title_hi="हाँ, मिटाएँ"),
                        Button(id="btn_delete_cancel", title_hi="नहीं"),
                    ],
                )
            ]

        # 3. ASK interrupt flow (§8.3 step 5, §8.4)
        is_ask_keyword = matched_intent == Intent.ASK or text_content.startswith(
            ("सवाल", "प्रश्न", "question", "sawal")
        )
        if is_ask_keyword or ctx.current_state == SessionStateEnum.ASK:
            if ctx.current_state != SessionStateEnum.ASK:
                ctx.prior_state_before_ask = ctx.current_state
                ctx.current_state = SessionStateEnum.ASK

            q_text = extract_ask_query(text_content) if is_ask_keyword else text_content
            if not q_text or q_text in ("सवाल", "प्रश्न"):
                await self._sync_context_to_db(ctx, teacher_id)
                return [
                    OutboundMessage(
                        kind="text",
                        text_hi=get_message("ask_clarify_generic", address_form),
                    )
                ]

            # Execute Question Classifier
            classify_res = await classify_question(
                q_text, clarifying_already_asked=ctx.clarifying_already_asked
            )

            if classify_res.output.needs_clarification and not ctx.clarifying_already_asked:
                ctx.clarifying_already_asked = True
                await self._sync_context_to_db(ctx, teacher_id)
                clarify_msg = classify_res.output.clarifying_question_hi or get_message(
                    "ask_clarify_generic", address_form
                )
                return [
                    OutboundMessage(
                        kind="text",
                        text_hi=clarify_msg,
                    )
                ]

            # Retrieval
            chunks = await self.retriever.retrieve(classify_res.output.search_query_hi or q_text)
            schema_chunks = [
                RetrievedChunk(
                    chunk_id=c.chunk_id,
                    source_short_hi=c.source,
                    section=c.section,
                    text=c.text,
                    score=c.similarity_score,
                )
                for c in chunks
            ]

            # Guide Answerer
            answer_res = await answer_guide_question(
                question=q_text,
                category=classify_res.output.category,
                chunks=schema_chunks,
                address_form=address_form,
            )

            # Persist question record
            status_val = "escalated" if answer_res.escalated else "answered"
            await self.repo.record_question(
                teacher_id=teacher_id,
                text=q_text,
                category=classify_res.output.category,
                answer_hi=answer_res.output.answer_hi,
                source_ids=answer_res.output.source_ids,
                confidence=answer_res.output.confidence,
                status=status_val,
            )

            # Compose reply
            if answer_res.escalated:
                reply_text = get_message("ask_escalated", address_form)
            elif classify_res.output.category == "out_of_scope":
                reply_text = get_message("ask_out_of_scope", address_form)
            elif classify_res.output.category == "admin":
                reply_text = get_message("ask_admin", address_form)
            else:
                reply_text = compose_guide_reply(answer_res.output, schema_chunks, address_form)

            # Resume prior state
            prior = ctx.prior_state_before_ask or SessionStateEnum.LEARN
            ctx.current_state = prior
            ctx.prior_state_before_ask = None
            ctx.clarifying_already_asked = False
            await self._sync_context_to_db(ctx, teacher_id)

            resume_note = get_message("ask_resume", address_form)
            prior_prompt_key = WeeklyStateMachine(ctx).get_state_prompt_key(prior)
            prior_prompt = get_message(prior_prompt_key, address_form)

            return [
                OutboundMessage(kind="text", text_hi=reply_text),
                OutboundMessage(kind="text", text_hi=f"{resume_note}\n\n{prior_prompt}"),
            ]

        # 4. Onboarding flow (§8.1)
        if ctx.onboarding_state != OnboardingStateEnum.READY:
            osm = OnboardingStateMachine(ctx)
            current_onboarding = ctx.onboarding_state

            if current_onboarding == OnboardingStateEnum.NEW:
                if matched_intent == Intent.CONFIRM_YES or btn_id == "btn_agree":
                    ctx.consent_service = True
                    await self.repo.log_consent(teacher_id, "consent_service", True)
                    osm.transition("btn_agree")
                    await self._sync_context_to_db(ctx, teacher_id)
                    return [
                        OutboundMessage(
                            kind="text",
                            text_hi=get_message("ask_join_code", address_form),
                        )
                    ]
                if matched_intent == Intent.MORE or btn_id == "btn_more":
                    return [
                        OutboundMessage(
                            kind="buttons",
                            text_hi=get_message("consent_details", address_form),
                            buttons=[
                                Button(
                                    id="btn_agree", title_hi=get_message("btn_agree", address_form)
                                ),
                                Button(
                                    id="btn_decline",
                                    title_hi=get_message("btn_decline", address_form),
                                ),
                            ],
                        )
                    ]
                if matched_intent == Intent.CONFIRM_NO or btn_id == "btn_decline":
                    await self.repo.log_consent(teacher_id, "consent_service", False)
                    return [
                        OutboundMessage(
                            kind="text",
                            text_hi=get_message("consent_declined", address_form),
                        )
                    ]

            elif current_onboarding == OnboardingStateEnum.JOIN_CODE:
                if matched_intent == Intent.CONFIRM_NO or text_content in (
                    "नहीं",
                    "no_code",
                    "skip",
                ):
                    ctx.cluster_id = "UNASSIGNED"
                    osm.transition("no_code")
                    await self._sync_context_to_db(ctx, teacher_id)
                    return [
                        OutboundMessage(
                            kind="text",
                            text_hi=get_message("ask_name", address_form),
                        )
                    ]
                # Validate invite code against DB
                invite = await self.repo.get_invite_code(text_content)
                if invite is not None:
                    ctx.cluster_id = invite.cluster_id
                    ctx.batch_id = invite.batch_id
                    ctx.district = invite.district
                    osm.transition("valid_code")
                    await self._sync_context_to_db(ctx, teacher_id)
                    return [
                        OutboundMessage(
                            kind="text",
                            text_hi=get_message("ask_name", address_form),
                        )
                    ]
                return [
                    OutboundMessage(
                        kind="text",
                        text_hi=get_message("join_code_invalid", address_form),
                    )
                ]

            elif current_onboarding == OnboardingStateEnum.PROFILE_NAME:
                osm.transition(text_content)
                await self._sync_context_to_db(ctx, teacher_id)
                return [
                    OutboundMessage(
                        kind="buttons",
                        text_hi=get_message("ask_address_form", address_form),
                        buttons=[
                            Button(id="btn_female", title_hi="शिक्षिका"),
                            Button(id="btn_male", title_hi="शिक्षक"),
                        ],
                    )
                ]

            elif current_onboarding == OnboardingStateEnum.PROFILE_ADDRESS:
                osm.transition(btn_id or text_content)
                await self._sync_context_to_db(ctx, teacher_id)
                return [
                    OutboundMessage(
                        kind="text",
                        text_hi=get_message(
                            "ask_experience", ctx.address_form, name=ctx.name or "शिक्षिका"
                        ),
                    )
                ]

            elif current_onboarding == OnboardingStateEnum.PROFILE_EXPERIENCE:
                osm.transition(text_content)
                await self._sync_context_to_db(ctx, teacher_id)
                return [
                    OutboundMessage(
                        kind="text",
                        text_hi=get_message("ask_classes", ctx.address_form),
                    )
                ]

            elif current_onboarding == OnboardingStateEnum.PROFILE_CLASSES:
                osm.transition(text_content)
                await self._sync_context_to_db(ctx, teacher_id)
                return [
                    OutboundMessage(
                        kind="buttons",
                        text_hi=get_message("consent_share_scores", ctx.address_form),
                        buttons=[
                            Button(id="btn_yes", title_hi="हाँ"),
                            Button(id="btn_no", title_hi="नहीं"),
                        ],
                    )
                ]

            elif current_onboarding == OnboardingStateEnum.SHARE_CONSENT:
                share_ok = matched_intent == Intent.CONFIRM_YES or btn_id == "btn_yes"
                ctx.consent_share_scores = share_ok
                await self.repo.log_consent(teacher_id, "consent_share_scores", share_ok)
                osm.transition("btn_yes" if share_ok else "btn_no")
                await self._sync_context_to_db(ctx, teacher_id)
                return [
                    OutboundMessage(
                        kind="text",
                        text_hi=get_message("placement_intro", ctx.address_form),
                    )
                ]

            elif current_onboarding == OnboardingStateEnum.PLACEMENT_INTRO:
                osm.transition("turn_input")
                # Initialize placement scene with Ravi
                scene = await scene_store.get_active_for_teacher(teacher_id)
                if scene is None:
                    scene = await self.scene_runner.create_scene(
                        teacher_id=teacher_id, move_id="NUM_SUB_REGROUP_BUNDLES"
                    )
                turn_res = None
                if scene is not None:
                    turn_res = await self.scene_runner.turn(
                        scene_id=scene.scene_id,
                        transcript=text_content,
                        address_form=ctx.address_form,
                    )
                await self._sync_context_to_db(ctx, teacher_id)
                turn1_outbounds = turn_res.outbound if turn_res else []
                if not turn1_outbounds:
                    turn1_outbounds = [
                        OutboundMessage(
                            kind="text",
                            text_hi="रवि: 45 ही तो होगा!",
                            speaker="ravi",
                        )
                    ]
                return turn1_outbounds

            elif current_onboarding == OnboardingStateEnum.PLACEMENT:
                res_placement = osm.transition(text_content)
                scene = await scene_store.get_active_for_teacher(teacher_id)
                turn_res = None
                if scene is not None:
                    turn_res = await self.scene_runner.turn(
                        scene_id=scene.scene_id,
                        transcript=text_content,
                        address_form=ctx.address_form,
                    )

                if res_placement.new_state == str(OnboardingStateEnum.READY):
                    # Placement finished after turn 2: compute personal move path
                    path_entries = compute_move_path(
                        teacher_id=teacher_id,
                        first_year=ctx.first_year,
                        classes=ctx.classes,
                        placement_used_tell_answer=False,
                    )
                    await self.repo.record_move_path(teacher_id, path_entries)
                    if path_entries:
                        ctx.current_move_id = path_entries[0].move_id
                    ctx.current_state = SessionStateEnum.LEARN
                    await self._sync_context_to_db(ctx, teacher_id)

                    ready_outbounds: list[OutboundMessage] = []
                    if turn_res:
                        ready_outbounds.extend(turn_res.outbound)
                    ready_outbounds.extend(
                        [
                            OutboundMessage(
                                kind="text", text_hi=get_message("placement_done", ctx.address_form)
                            ),
                            OutboundMessage(
                                kind="text",
                                text_hi=get_message(
                                    "ready_first_move",
                                    ctx.address_form,
                                    move_title="स्थानीय मान - बंडल",
                                ),
                            ),
                            OutboundMessage(
                                kind="buttons",
                                text_hi=get_message(
                                    "learn_intro", ctx.address_form, move_title="स्थानीय मान - बंडल"
                                ),
                                buttons=[
                                    Button(
                                        id="btn_understood",
                                        title_hi=get_message("btn_understood", ctx.address_form),
                                    ),
                                    Button(
                                        id="btn_replay",
                                        title_hi=get_message("btn_replay", ctx.address_form),
                                    ),
                                ],
                            ),
                        ]
                    )
                    return ready_outbounds

                await self._sync_context_to_db(ctx, teacher_id)
                return turn_res.outbound if turn_res else []

        # 5. Weekly Loop Flow (§8.2)
        wsm = WeeklyStateMachine(ctx)
        curr = ctx.current_state

        if curr == SessionStateEnum.LEARN:
            if matched_intent == Intent.REPEAT or btn_id == "btn_replay":
                return [
                    OutboundMessage(
                        kind="buttons",
                        text_hi=get_message("learn_intro", address_form),
                        buttons=[
                            Button(
                                id="btn_understood",
                                title_hi=get_message("btn_understood", address_form),
                            ),
                            Button(
                                id="btn_replay", title_hi=get_message("btn_replay", address_form)
                            ),
                        ],
                    )
                ]
            if matched_intent == Intent.NEXT or btn_id == "btn_understood":
                wsm.transition("btn_understood")
                await self._sync_context_to_db(ctx, teacher_id)
                return [
                    OutboundMessage(
                        kind="buttons",
                        text_hi=get_message("explain_back_prompt", address_form),
                        buttons=[
                            Button(id="btn_skip", title_hi=get_message("btn_skip", address_form)),
                        ],
                    )
                ]
            # Free text does NOT silently advance (§8.3 step 4)
            return [
                OutboundMessage(
                    kind="text",
                    text_hi=get_message("unclear", address_form),
                )
            ]

        elif curr == SessionStateEnum.EXPLAIN_BACK:
            if matched_intent == Intent.SKIP or btn_id == "btn_skip":
                wsm.transition("btn_skip")
                await self._sync_context_to_db(ctx, teacher_id)
                return [
                    OutboundMessage(
                        kind="buttons",
                        text_hi=get_message("model_offer", address_form),
                        buttons=[
                            Button(
                                id="btn_listen", title_hi=get_message("btn_listen", address_form)
                            ),
                            Button(id="btn_skip", title_hi=get_message("btn_skip", address_form)),
                        ],
                    )
                ]
            # Evaluate teacher explanation via check_fidelity
            move = load_move_card(ctx.current_move_id)
            try:
                fidelity_res = await check_fidelity(move, text_content)
            except Exception as exc:
                logger.warning("Fidelity check failed: %s; using deterministic fallback", exc)
                from backend.app.llm.roles.fidelity_checker import (
                    FidelityResult,
                    compose_fidelity_reply,
                    fallback_fidelity,
                )

                fidelity_fb = fallback_fidelity(move=move, transcript=text_content)
                reply_hi = compose_fidelity_reply(move, fidelity_fb)
                fidelity_res = FidelityResult(
                    output=fidelity_fb,
                    reply_hi=reply_hi,
                    needs_review=True,
                    review_reason=f"Fallback fidelity checker used: {exc}",
                    used_fallback=True,
                )

            # Persist explain score
            await self.repo.record_explain_score(
                teacher_id=teacher_id,
                move_id=ctx.current_move_id,
                transcript=text_content,
                points={p.id: p.status for p in fidelity_res.output.points},
                misconceptions=fidelity_res.output.misconceptions,
                confidence=fidelity_res.output.confidence,
                needs_review=fidelity_res.needs_review,
            )

            wsm.transition(text_content)
            await self._sync_context_to_db(ctx, teacher_id)

            reply_text = fidelity_res.reply_hi or get_message("model_offer", address_form)
            return [
                OutboundMessage(kind="text", text_hi=reply_text),
                OutboundMessage(
                    kind="buttons",
                    text_hi=get_message("model_offer", address_form),
                    buttons=[
                        Button(id="btn_listen", title_hi=get_message("btn_listen", address_form)),
                        Button(id="btn_skip", title_hi=get_message("btn_skip", address_form)),
                    ],
                ),
            ]

        elif curr == SessionStateEnum.MODEL:
            if matched_intent == Intent.LISTEN or btn_id == "btn_listen":
                wsm.transition("btn_listen")
                await self._sync_context_to_db(ctx, teacher_id)
                return [
                    OutboundMessage(kind="text", text_hi=get_message("model_header", address_form)),
                    OutboundMessage(
                        kind="text",
                        text_hi=get_message("rehearse_intro", address_form, scene_intro="कक्षा 2 में"),
                    ),
                ]
            if matched_intent == Intent.SKIP or btn_id == "btn_skip":
                wsm.transition("btn_skip")
                await self._sync_context_to_db(ctx, teacher_id)
                return [
                    OutboundMessage(
                        kind="text",
                        text_hi=get_message("rehearse_intro", address_form, scene_intro="कक्षा 2 में"),
                    ),
                ]
            # Free text does NOT silently advance
            return [
                OutboundMessage(
                    kind="text",
                    text_hi=get_message("unclear", address_form),
                )
            ]

        elif curr == SessionStateEnum.REHEARSE_INTRO:
            # First turn begins rehearsal
            wsm.transition("start_turn")
            scene = await scene_store.get_active_for_teacher(teacher_id)
            if scene is None:
                scene = await self.scene_runner.create_scene(
                    teacher_id=teacher_id, move_id=ctx.current_move_id
                )

            turn_res = await self.scene_runner.turn(
                scene_id=scene.scene_id,
                transcript=text_content,
                address_form=address_form,
            )
            await self._sync_context_to_db(ctx, teacher_id)
            return turn_res.outbound

        elif curr == SessionStateEnum.REHEARSE:
            scene = await scene_store.get_active_for_teacher(teacher_id)
            if scene is None:
                scene = await self.scene_runner.create_scene(
                    teacher_id=teacher_id, move_id=ctx.current_move_id
                )

            turn_res = await self.scene_runner.turn(
                scene_id=scene.scene_id,
                transcript=text_content,
                address_form=address_form,
            )
            ended = turn_res.turn.ended or matched_intent == Intent.STOP_SCENE

            if ended:
                wsm_res = wsm.transition(text_content, scene_ended=True)
                if wsm_res.evidence_level and wsm_res.evidence_level >= 1:
                    await self.repo.record_adoption_evidence(
                        teacher_id=teacher_id,
                        move_id=ctx.current_move_id,
                        level=1,
                        source="rehearsal",
                        detail={"turns": ctx.rehearsal_turns_count},
                    )

                # Generate coach feedback
                move = load_move_card(ctx.current_move_id)
                teacher_turns = [
                    SceneTurn(speaker="teacher", text_hi=t.transcript)
                    for t in scene.turns
                    if t.transcript
                ]
                try:
                    coach_res = await coach_feedback(
                        move=move,
                        turns=teacher_turns,
                        acts=[[TeachingAct.REPEAT_QUESTION] for _ in teacher_turns],
                        trajectories={"ravi": [ChildState.MISCONCEPTION, ChildState.CORRECT]},
                        target_child_id="ravi",
                        current_item_answer=35,
                        attempt=ctx.retries_count + 1,
                    )
                except Exception as exc:
                    logger.warning("Coach feedback failed: %s; using deterministic fallback", exc)
                    from backend.app.llm.roles.coach import CoachResult, fallback_coach_feedback

                    coach_fb = fallback_coach_feedback(
                        move=move,
                        turns=teacher_turns,
                        acts=[[TeachingAct.REPEAT_QUESTION] for _ in teacher_turns],
                        trajectories={"ravi": [ChildState.MISCONCEPTION, ChildState.CORRECT]},
                        target_child_id="ravi",
                        current_item_answer=35,
                        attempt=ctx.retries_count + 1,
                    )
                    coach_res = CoachResult(
                        feedback=coach_fb,
                        needs_review=True,
                        review_reason=f"Fallback coach used: {exc}",
                        used_fallback=True,
                    )

                score_entry = await self.repo.record_rehearsal_score(
                    teacher_id=teacher_id,
                    scene_id=scene.scene_id,
                    move_id=ctx.current_move_id,
                    attempt=ctx.retries_count + 1,
                    scores=coach_res.feedback.scores,
                    evidence={},
                    strength_hi=coach_res.feedback.strength_hi,
                    change_hi=coach_res.feedback.change_hi,
                    exact_words_hi=coach_res.feedback.exact_words_hi,
                    confidence=coach_res.feedback.confidence,
                    needs_review=coach_res.needs_review,
                )

                if coach_res.needs_review:
                    await self.repo.record_review_item(
                        kind="rehearsal_score",
                        ref_id=str(score_entry.id),
                        reason=coach_res.review_reason,
                    )

                prefix = (
                    f"{get_message('coach_low_conf_prefix', address_form)}\n\n"
                    if coach_res.needs_review
                    else ""
                )
                feedback_body = get_message(
                    "feedback_body",
                    address_form,
                    strength=coach_res.feedback.strength_hi,
                    change=coach_res.feedback.change_hi,
                    exact_words=coach_res.feedback.exact_words_hi,
                )

                await self._sync_context_to_db(ctx, teacher_id)
                coach_outbounds: list[OutboundMessage] = list(turn_res.outbound)
                coach_outbounds.extend(
                    [
                        OutboundMessage(
                            kind="text", text_hi=get_message("feedback_header", address_form)
                        ),
                        OutboundMessage(kind="text", text_hi=f"{prefix}{feedback_body}"),
                        OutboundMessage(
                            kind="buttons",
                            text_hi=get_message("realism_prompt", address_form),
                            buttons=[
                                Button(
                                    id="btn_retry", title_hi=get_message("btn_retry", address_form)
                                ),
                                Button(
                                    id="btn_continue",
                                    title_hi=get_message("btn_continue", address_form),
                                ),
                            ],
                        ),
                    ]
                )
                return coach_outbounds

            wsm.transition(text_content)
            await self._sync_context_to_db(ctx, teacher_id)
            return turn_res.outbound

        elif curr == SessionStateEnum.FEEDBACK:
            if matched_intent == Intent.RETRY or btn_id == "btn_retry":
                res = wsm.transition("btn_retry")
                await self._sync_context_to_db(ctx, teacher_id)
                if res.new_state == "REHEARSE_INTRO":
                    return [
                        OutboundMessage(
                            kind="text",
                            text_hi=get_message(
                                "rehearse_intro", address_form, scene_intro="कक्षा 2 में नया अभ्यास:"
                            ),
                        )
                    ]
                return [
                    OutboundMessage(kind="text", text_hi=get_message("retry_limit", address_form)),
                    OutboundMessage(
                        kind="buttons",
                        text_hi=get_message("try_in_class", address_form),
                        buttons=[
                            Button(id="btn_peer", title_hi=get_message("btn_peer", address_form)),
                            Button(id="btn_self", title_hi=get_message("btn_self", address_form)),
                            Button(id="btn_later", title_hi=get_message("btn_later", address_form)),
                        ],
                    ),
                ]
            if matched_intent == Intent.NEXT or btn_id == "btn_continue":
                wsm.transition("btn_continue")
                await self._sync_context_to_db(ctx, teacher_id)
                return [
                    OutboundMessage(
                        kind="buttons",
                        text_hi=get_message("try_in_class", address_form),
                        buttons=[
                            Button(id="btn_peer", title_hi=get_message("btn_peer", address_form)),
                            Button(id="btn_self", title_hi=get_message("btn_self", address_form)),
                            Button(id="btn_later", title_hi=get_message("btn_later", address_form)),
                        ],
                    )
                ]
            # Realism rating
            return []

        elif curr == SessionStateEnum.TRY_IN_CLASS:
            if matched_intent == Intent.PEER or btn_id == "btn_peer":
                wsm.transition("btn_peer")
                await self._sync_context_to_db(ctx, teacher_id)
                return [
                    OutboundMessage(
                        kind="buttons",
                        text_hi=get_message(
                            "peer_item",
                            address_form,
                            i=1,
                            n=3,
                            item="क्या शिक्षक ने बंडलों का उपयोग किया?",
                        ),
                        buttons=[
                            Button(id="btn_yes", title_hi="हाँ"),
                            Button(id="btn_no", title_hi="नहीं"),
                        ],
                    )
                ]
            if matched_intent == Intent.SELF or btn_id == "btn_self":
                wsm.transition("btn_self")
                await self._sync_context_to_db(ctx, teacher_id)
                return [
                    OutboundMessage(
                        kind="text",
                        text_hi=get_message(
                            "reflect_q",
                            address_form,
                            i=1,
                            question="आज कक्षा में बच्चों को क्या सबसे अच्छा लगा?",
                        ),
                    )
                ]
            if matched_intent == Intent.LATER or btn_id == "btn_later":
                wsm.transition("btn_later")
                await self._sync_context_to_db(ctx, teacher_id)
                return [
                    OutboundMessage(
                        kind="text",
                        text_hi=get_message("reminder", address_form, name=ctx.name or "शिक्षिका"),
                    )
                ]
            # Free text does not advance
            return [
                OutboundMessage(
                    kind="text",
                    text_hi=get_message("unclear", address_form),
                )
            ]

        elif curr == SessionStateEnum.REFLECT_PEER:
            res = wsm.transition(text_content)
            if res.new_state == "DONE":
                await self.repo.record_adoption_evidence(
                    teacher_id=teacher_id,
                    move_id=ctx.current_move_id,
                    level=3,
                    source="peer_checklist",
                )
                await self._sync_context_to_db(ctx, teacher_id)
                level_name = get_message("evidence_level_3", address_form)
                return [
                    OutboundMessage(
                        kind="buttons",
                        text_hi=get_message(
                            "week_done",
                            address_form,
                            name=ctx.name or "शिक्षिका",
                            level_name=level_name,
                            next_move_title="घटाना - पुनर्समूहन",
                        ),
                        buttons=[
                            Button(
                                id="btn_next_move",
                                title_hi=get_message("btn_next_move", address_form),
                            ),
                            Button(
                                id="btn_progress",
                                title_hi=get_message("btn_progress", address_form),
                            ),
                        ],
                    )
                ]
            await self._sync_context_to_db(ctx, teacher_id)
            return [
                OutboundMessage(
                    kind="buttons",
                    text_hi=get_message(
                        "peer_item",
                        address_form,
                        i=ctx.reflect_step,
                        n=3,
                        item="क्या बच्चों ने समझाकर उत्तर दिया?",
                    ),
                    buttons=[
                        Button(id="btn_yes", title_hi="हाँ"),
                        Button(id="btn_no", title_hi="नहीं"),
                    ],
                )
            ]

        elif curr == SessionStateEnum.REFLECT_SELF:
            res = wsm.transition(text_content)
            if res.new_state == "DONE":
                await self.repo.record_adoption_evidence(
                    teacher_id=teacher_id,
                    move_id=ctx.current_move_id,
                    level=2,
                    source="reflection",
                )
                await self._sync_context_to_db(ctx, teacher_id)
                level_name = get_message("evidence_level_2", address_form)
                return [
                    OutboundMessage(
                        kind="buttons",
                        text_hi=get_message(
                            "week_done",
                            address_form,
                            name=ctx.name or "शिक्षिका",
                            level_name=level_name,
                            next_move_title="घटाना - पुनर्समूहन",
                        ),
                        buttons=[
                            Button(
                                id="btn_next_move",
                                title_hi=get_message("btn_next_move", address_form),
                            ),
                            Button(
                                id="btn_progress",
                                title_hi=get_message("btn_progress", address_form),
                            ),
                        ],
                    )
                ]
            await self._sync_context_to_db(ctx, teacher_id)
            return [
                OutboundMessage(
                    kind="text",
                    text_hi=get_message(
                        "reflect_q", address_form, i=2, question="अगली बार आप क्या अलग करेंगी?"
                    ),
                )
            ]

        elif curr == SessionStateEnum.DONE:
            if matched_intent == Intent.NEXT or btn_id == "btn_next_move":
                wsm.transition("btn_next_move")
                await self._sync_context_to_db(ctx, teacher_id)
                return [
                    OutboundMessage(
                        kind="buttons",
                        text_hi=get_message("learn_intro", address_form),
                        buttons=[
                            Button(
                                id="btn_understood",
                                title_hi=get_message("btn_understood", address_form),
                            ),
                            Button(
                                id="btn_replay", title_hi=get_message("btn_replay", address_form)
                            ),
                        ],
                    )
                ]
            if matched_intent == Intent.PROGRESS or btn_id == "btn_progress":
                return [
                    OutboundMessage(
                        kind="text",
                        text_hi=get_message(
                            "progress_summary", address_form, n_done=1, lines="1. स्थानीय मान - बंडल"
                        ),
                    )
                ]
            return [
                OutboundMessage(
                    kind="text",
                    text_hi=get_message("unclear", address_form),
                )
            ]

        return []


__all__ = [
    "SessionService",
]
