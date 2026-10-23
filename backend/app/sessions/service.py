"""SessionService orchestrating conversation flow, state machine, and DB side effects (spec/08, T20/T21)."""

from __future__ import annotations

import logging
import unicodedata
import uuid
from datetime import UTC, date, datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.class_profile import flow as class_flow
from backend.app.class_profile import personalise
from backend.app.config import settings
from backend.app.content_models import MoveCard
from backend.app.core.intents import (
    BUTTON_INTENT_MAP,
    Intent,
    extract_ask_query,
    match_intent,
)
from backend.app.core.messages import get_message
from backend.app.core.types import Button, Citation, InboundMessage, OutboundMessage
from backend.app.db.models import Message
from backend.app.llm.client import LLMUnavailable
from backend.app.llm.roles.coach import coach_feedback
from backend.app.llm.roles.coach_suggestion import suggest_from_sources
from backend.app.llm.roles.fidelity_checker import check_fidelity
from backend.app.llm.roles.guide_answerer import (
    answer_guide_question,
    citations_for_chunks,
    compose_guide_reply,
    format_guide_citation,
)
from backend.app.llm.roles.module_check import check_module
from backend.app.llm.roles.question_classifier import classify_question
from backend.app.llm.schemas import RetrievedChunk
from backend.app.rehearsal.diagnosis import DiagnosisResult
from backend.app.rehearsal.scene_runner import ChildLineRecord, SceneRunner, load_move_card
from backend.app.rehearsal.scene_store import scene_store
from backend.app.retrieval.search import GuideRetriever, get_guide_retriever
from backend.app.rule_engine.domain import (
    ChildRuntime,
    ChildState,
    Problem,
    SceneTurn,
    TeachingAct,
)
from backend.app.sessions import modules, rehearse_setup
from backend.app.sessions.path import MovePathEntry, compute_move_path, load_induction_order
from backend.app.sessions.path_score import DONE_MIN_EVIDENCE
from backend.app.sessions.repository import SessionRepository
from backend.app.sessions.state_machine import (
    ONBOARDING_PROMPT_KEYS,
    OnboardingStateEnum,
    OnboardingStateMachine,
    SessionContext,
    SessionStateEnum,
    WeeklyStateMachine,
)
from backend.app.sessions.training_rating import (
    is_rating_escape,
    is_skip_comment,
    parse_training_rating,
)

logger = logging.getLogger("abhyas.sessions.service")
IST = ZoneInfo("Asia/Kolkata")


class SessionService:
    """Orchestrates deliberate practice conversation sessions, state transitions, and database side effects."""

    def __init__(
        self,
        repository: SessionRepository | None = None,
        db_session: AsyncSession | None = None,
        scene_runner: SceneRunner | None = None,
    ) -> None:
        if repository is not None:
            self.repo = repository
        elif db_session is not None:
            self.repo = SessionRepository(db_session)
        else:
            raise ValueError("Either repository or db_session must be provided to SessionService.")
        self.scene_runner = scene_runner or SceneRunner()
        self.retriever: GuideRetriever = get_guide_retriever()

    async def _learn_intro(
        self, move: MoveCard, address_form: str, struggle_ids: list[str] | None = None
    ) -> tuple[str, list[Citation]]:
        """Learn-step intro, plus the best matching official excerpt for the move's topic.

        The excerpt comes from the ingested source documents only (never move cards). When nothing
        scores above RETRIEVAL_MIN_SCORE the intro is returned unchanged.
        """
        intro = get_message("learn_intro", address_form, move_title=move.title_hi)
        reason = personalise.because(move.id, struggle_ids or [])
        if reason is not None:
            because_line = get_message(
                "ui_class_chosen_because", label=personalise.label_of(reason)
            )
            intro = f"{because_line}\n\n{intro}"
        query = f"{move.title_hi} {' '.join(t.replace('_', ' ') for t in move.tags)}"
        hits = await self.retriever.retrieve(
            query, top_k=1, min_score=settings.RETRIEVAL_MIN_SCORE, official_only=True
        )
        if not hits or not hits[0].gloss_hi:
            return intro, []
        hit = hits[0]
        chunk = RetrievedChunk(
            chunk_id=hit.chunk_id,
            source_short_hi=hit.source_short_hi,
            section=hit.section,
            page=hit.page,
            text=hit.text,
            score=hit.similarity_score,
        )
        cites = citations_for_chunks([chunk], address_form)
        ref = get_message(
            "learn_reference",
            address_form,
            summary=hit.gloss_hi,
            citation=cites[0].line_hi if cites else "",
        )
        return f"{intro}\n\n{ref}", cites

    async def get_or_create_context(self, teacher_id: UUID) -> SessionContext:
        """Loads or constructs a SessionContext from database state."""
        teacher = await self.repo.get_or_create_teacher(teacher_id)
        today = datetime.now(IST).date()
        week_start = today - timedelta(days=today.weekday())

        path_entries = await self.repo.get_move_path(teacher_id)
        if path_entries and path_entries[0].move_id:
            initial_move_id = path_entries[0].move_id
        else:
            initial_move_id = load_induction_order()[0]

        db_session = await self.repo.get_or_create_session_state(
            teacher_id=teacher_id,
            week_start=week_start,
            move_id=initial_move_id,
        )

        ctx_data = db_session.context or {}
        ctx = SessionContext(
            teacher_id=str(teacher_id),
            week_start=str(week_start),
            current_move_id=db_session.move_id,
            current_state=SessionStateEnum(db_session.state),
            prior_state_before_ask=(
                SessionStateEnum(db_session.prior_state) if db_session.prior_state else None
            ),
            prior_state_before_delete=(
                SessionStateEnum(ctx_data["prior_state_before_delete"])
                if ctx_data.get("prior_state_before_delete")
                else None
            ),
            awaiting_delete_confirm=bool(ctx_data.get("awaiting_delete_confirm", False)),
            onboarding_state=OnboardingStateEnum(teacher.onboarding_state),
            retries_count=db_session.rehearse_attempts,
            rehearsal_turns_count=int(ctx_data.get("rehearsal_turns_count", 0)),
            placement_turns_count=int(ctx_data.get("placement_turns_count", 0)),
            reflection_type=ctx_data.get("reflection_type"),
            reflect_step=int(ctx_data.get("reflect_step", 0)),
            peer_checklist_total=int(ctx_data.get("peer_checklist_total", 3)),
            evidence_level=int(ctx_data.get("evidence_level", 0)),
            child_states=ctx_data.get("child_states", {}),
            clarifying_already_asked=bool(ctx_data.get("clarifying_already_asked", False)),
            rating_stage=str(ctx_data.get("rating_stage", "")),
            rating_level=int(ctx_data.get("rating_level", 0)),
            rating_unclear=int(ctx_data.get("rating_unclear", 0)),
            module_mode=bool(ctx_data.get("module_mode", False)),
            module_check_stage=str(ctx_data.get("module_check_stage", "")),
            rehearse_stage=str(ctx_data.get("rehearse_stage", "")),
            rehearse_mode=str(ctx_data.get("rehearse_mode", "")),
            rehearse_child=str(ctx_data.get("rehearse_child", "")),
            resume_scene_id=str(ctx_data.get("resume_scene_id", "")),
            diagnosis=dict(ctx_data.get("diagnosis") or {}),
            class_stage=str(ctx_data.get("class_stage", "")),
            class_pending=[str(i) for i in ctx_data.get("class_pending") or []],
            class_struggles=[str(i) for i in teacher.class_struggles or []],
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
        teacher.class_struggles = list(ctx.class_struggles)
        await self.repo.save_teacher(teacher)

        week_d = date.fromisoformat(ctx.week_start)
        db_state = await self.repo.get_or_create_session_state(
            teacher_uuid, week_d, ctx.current_move_id
        )
        db_state.move_id = ctx.current_move_id
        db_state.state = ctx.current_state.value
        db_state.prior_state = (
            ctx.prior_state_before_ask.value if ctx.prior_state_before_ask else None
        )
        db_state.rehearse_attempts = ctx.retries_count
        db_state.context = {
            "evidence_level": ctx.evidence_level,
            "rehearsal_turns_count": ctx.rehearsal_turns_count,
            "placement_turns_count": ctx.placement_turns_count,
            "reflect_step": ctx.reflect_step,
            "reflection_type": ctx.reflection_type,
            "peer_checklist_total": ctx.peer_checklist_total,
            "child_states": ctx.child_states,
            "awaiting_delete_confirm": ctx.awaiting_delete_confirm,
            "prior_state_before_delete": (
                ctx.prior_state_before_delete.value if ctx.prior_state_before_delete else None
            ),
            "clarifying_already_asked": ctx.clarifying_already_asked,
            "rating_stage": ctx.rating_stage,
            "rating_level": ctx.rating_level,
            "rating_unclear": ctx.rating_unclear,
            "module_mode": ctx.module_mode,
            "module_check_stage": ctx.module_check_stage,
            "rehearse_stage": ctx.rehearse_stage,
            "rehearse_mode": ctx.rehearse_mode,
            "rehearse_child": ctx.rehearse_child,
            "resume_scene_id": ctx.resume_scene_id,
            "diagnosis": ctx.diagnosis,
            "class_stage": ctx.class_stage,
            "class_pending": ctx.class_pending,
        }
        await self.repo.save_session_state(db_state)
        if (
            self.repo.session is not None
            and ctx.onboarding_state == OnboardingStateEnum.READY
            and ctx.current_state != SessionStateEnum.DONE
        ):
            try:
                from backend.app.jobs.handlers import schedule_reminder

                async with self.repo.session.begin_nested():
                    await schedule_reminder(self.repo.session, teacher_uuid, now=datetime.now(UTC))
            except (SQLAlchemyError, ValueError):
                logger.warning("Could not schedule reminder", exc_info=True)

    async def _get_next_move_title(self, teacher_id: UUID, current_move_id: str) -> str:
        """Determines next move title from teacher's personal move path."""
        path_entries = await self.repo.get_move_path(teacher_id)
        if path_entries:
            curr_idx = next(
                (i for i, p in enumerate(path_entries) if p.move_id == current_move_id),
                -1,
            )
            if curr_idx >= 0 and curr_idx + 1 < len(path_entries):
                next_id = path_entries[curr_idx + 1].move_id
                if next_id:
                    next_card = load_move_card(next_id)
                    return next_card.title_hi
        curr_card = load_move_card(current_move_id)
        return curr_card.title_hi

    def _get_resume_prompt(
        self,
        ctx: SessionContext,
        prior: SessionStateEnum,
        address_form: str,
    ) -> str:
        """Constructs prompt message to resume prior state after an ASK interruption."""
        if ctx.onboarding_state != OnboardingStateEnum.READY:
            prompt_key = ONBOARDING_PROMPT_KEYS.get(ctx.onboarding_state, "welcome")
            return get_message(prompt_key, address_form)
        prior_prompt_key = WeeklyStateMachine(ctx).get_state_prompt_key(prior)
        move = load_move_card(ctx.current_move_id)
        if prior_prompt_key == "learn_intro":
            return get_message(prior_prompt_key, address_form, move_title=move.title_hi)
        elif prior_prompt_key == "rehearse_intro":
            return get_message(prior_prompt_key, address_form, scene_intro=move.scenario.intro_hi)
        else:
            return get_message(prior_prompt_key, address_form)

    async def _week_done_messages(
        self, ctx: SessionContext, teacher_id: UUID, level: int
    ) -> list[OutboundMessage]:
        """The end-of-week message with the evidence level reached and the next move."""
        address_form = ctx.address_form
        level_name = get_message(f"evidence_level_{level}", address_form)
        next_title = await self._get_next_move_title(teacher_id, ctx.current_move_id)
        default_name = (
            get_message("btn_female", address_form)
            if address_form == "f"
            else get_message("btn_male", address_form)
        )
        return [
            OutboundMessage(
                kind="buttons",
                text_hi=get_message(
                    "week_done",
                    address_form,
                    name=ctx.name or default_name,
                    level_name=level_name,
                    next_move_title=next_title,
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

    async def _begin_training_rating(
        self, ctx: SessionContext, teacher_id: UUID, level: int
    ) -> list[OutboundMessage]:
        """After REFLECT: "did it help your class?" (when she named a struggle this move practises),
        then the 1-5 usefulness rating, before the week_done message."""
        ctx.rating_unclear = 0
        ctx.rating_level = level
        if personalise.because(ctx.current_move_id, ctx.class_struggles) is not None:
            ctx.rating_stage = "helped"
            await self._sync_context_to_db(ctx, teacher_id)
            return [class_flow.helped_message()]
        ctx.rating_stage = "rating"
        await self._sync_context_to_db(ctx, teacher_id)
        return [
            OutboundMessage(
                kind="buttons",
                text_hi=get_message("rate_training_prompt", ctx.address_form),
                buttons=self._rating_buttons(ctx.address_form),
            )
        ]

    @staticmethod
    def _rating_buttons(address_form: str) -> list[Button]:
        """Three quick taps for the anchors; 2 and 4 (and all of 1-5) can be typed or spoken."""
        return [
            Button(id=f"btn_trate_{n}", title_hi=get_message(f"btn_trate_{n}", address_form))
            for n in (1, 3, 5)
        ]

    async def _source_suggestion(
        self, move: MoveCard, change_hi: str, address_form: str
    ) -> OutboundMessage | None:
        """One tip from the FLN training package after a scene, with a tappable citation.

        No retrieval support (or a failed guard) means no suggestion: nothing is invented.
        """
        try:
            hits = await self.retriever.retrieve(
                f"{move.title_hi} {change_hi}",
                top_k=settings.COACH_SUGGESTION_POOL,
                min_score=settings.RETRIEVAL_MIN_SCORE,
                official_only=True,
                min_matched_terms=settings.RETRIEVAL_MIN_MATCHED_TERMS,
            )
            chunks = [
                RetrievedChunk(
                    chunk_id=c.chunk_id,
                    source_short_hi=getattr(c, "source_short_hi", None) or c.source,
                    section=c.section,
                    page=c.page,
                    text=c.text,
                    gloss_hi=c.gloss_hi,
                    keywords_hi=c.keywords_hi,
                    score=c.similarity_score,
                )
                for c in hits
                if c.source == settings.COACH_SUGGESTION_SOURCE_ID
            ][: settings.COACH_SUGGESTION_CANDIDATES]
            result = await suggest_from_sources(move.title_hi, change_hi, chunks)
        except (LLMUnavailable, TimeoutError, ValueError, OSError) as exc:
            logger.warning("coach source suggestion skipped: %s", exc)
            return None
        if not result.suggestion_hi or result.chunk is None:
            return None
        cite = format_guide_citation(
            result.chunk.source_short_hi, result.chunk.page, address_form=address_form
        )
        return OutboundMessage(
            kind="text",
            text_hi=(
                f"{get_message('coach_source_suggestion', address_form, suggestion=result.suggestion_hi)}"
                f"\n\n{cite}"
            ),
            citations=citations_for_chunks([result.chunk], address_form),
        )

    async def _begin_rehearse_setup(
        self, ctx: SessionContext, teacher_id: UUID, move: MoveCard
    ) -> list[OutboundMessage]:
        """Entering REHEARSE_INTRO: offer 1-1 or three children (group-only moves: old intro)."""
        messages = rehearse_setup.begin_setup(ctx, move)
        await self._sync_context_to_db(ctx, teacher_id)
        return messages

    def _realism_prompt(self, ctx: SessionContext, address_form: str) -> str:
        """The realism question names the child in a 1-1 scene, otherwise 'these children'."""
        if ctx.rehearse_mode == rehearse_setup.MODE_ONE_ON_ONE and ctx.rehearse_child:
            return get_message(
                "realism_prompt_one_on_one",
                address_form,
                child=rehearse_setup.child_name(ctx.rehearse_child),
            )
        return get_message("realism_prompt", address_form)

    async def _resume_scene(self, ctx: SessionContext, teacher_id: UUID) -> bool:
        """Reopens the scene that ended too early; False if it is gone."""
        try:
            scene_id = UUID(ctx.resume_scene_id)
        except ValueError:
            return False
        scene = await scene_store.get(scene_id)
        if scene is None or scene.teacher_id != teacher_id:
            return False
        scene.active = True
        scene.scene_state.ended = False
        scene.scene_state.end_reason = None
        await scene_store.save(scene)
        ctx.current_state = SessionStateEnum.REHEARSE
        ctx.resume_scene_id = ""
        await self._sync_context_to_db(ctx, teacher_id)
        return True

    async def _clear_rating_stage(self, ctx: SessionContext, teacher_id: UUID) -> None:
        ctx.rating_stage = ""
        ctx.rating_level = 0
        ctx.rating_unclear = 0
        await self._sync_context_to_db(ctx, teacher_id)

    async def _handle_training_rating(
        self, ctx: SessionContext, teacher_id: UUID, text: str, btn_id: str | None
    ) -> list[OutboundMessage]:
        """Reads the rating (button, typed digit or spoken number), then the optional comment."""
        address_form = ctx.address_form
        if ctx.rating_stage == "helped":
            answer = class_flow.parse_helped(text, btn_id)
            if answer is None and ctx.rating_unclear < settings.CLASS_HELPED_MAX_UNCLEAR:
                ctx.rating_unclear += 1
                await self._sync_context_to_db(ctx, teacher_id)
                return [class_flow.helped_message()]
            ctx.rating_stage = "rating"
            ctx.rating_unclear = 0
            await self._sync_context_to_db(ctx, teacher_id)
            rating_prompt = OutboundMessage(
                kind="buttons",
                text_hi=get_message("rate_training_prompt", address_form),
                buttons=self._rating_buttons(address_form),
            )
            if answer is None:  # never trap her: nothing stored, on to the rating
                return [rating_prompt]
            await self.repo.record_class_outcome(
                teacher_id, ctx.current_move_id, answer, ctx.class_struggles
            )
            thanks = OutboundMessage(kind="text", text_hi=get_message("class_helped_thanks"))
            return [thanks, rating_prompt]
        if ctx.rating_stage == "rating":
            value = parse_training_rating(text, btn_id)
            if value is None and ctx.rating_unclear >= settings.TRAINING_RATING_MAX_UNCLEAR:
                # Second unclear reply: never trap the teacher. Skip the rating, store nothing.
                level = ctx.rating_level or ctx.evidence_level
                await self._clear_rating_stage(ctx, teacher_id)
                return await self._week_done_messages(ctx, teacher_id, level)
            if value is None:
                ctx.rating_unclear += 1
                await self._sync_context_to_db(ctx, teacher_id)
                return [
                    OutboundMessage(
                        kind="buttons",
                        text_hi=get_message("rate_training_unclear", address_form),
                        buttons=self._rating_buttons(address_form),
                    )
                ]
            await self.repo.record_training_rating(
                teacher_id=teacher_id, rating=value, move_id=ctx.current_move_id
            )
            ctx.rating_stage = "comment"
            await self._sync_context_to_db(ctx, teacher_id)
            return [
                OutboundMessage(
                    kind="buttons",
                    text_hi=get_message("rate_training_comment_prompt", address_form),
                    buttons=[
                        Button(id="btn_trate_skip", title_hi=get_message("btn_skip", address_form))
                    ],
                )
            ]

        # comment stage: free text (typed or transcribed from a voice note) or Skip
        comment = unicodedata.normalize("NFC", text).strip()
        skipped = btn_id == "btn_trate_skip" or is_skip_comment(comment)
        if comment and not skipped:
            await self.repo.set_training_comment(
                teacher_id, comment[: settings.TRAINING_COMMENT_MAX_CHARS]
            )
        level = ctx.rating_level or ctx.evidence_level
        await self._clear_rating_stage(ctx, teacher_id)
        thanks = OutboundMessage(
            kind="text", text_hi=get_message("rate_training_thanks", address_form)
        )
        return [thanks, *await self._week_done_messages(ctx, teacher_id, level)]

    async def _after_class_saved(self, ctx: SessionContext, teacher_id: UUID) -> None:
        """Her class choice changed: moves that practise it come first on her path."""
        rows = await self.repo.get_move_path(teacher_id)
        entries = [MovePathEntry(r.position, r.move_id, r.reason or "") for r in rows if r.move_id]
        if not entries:
            return
        done = await self.repo.done_move_ids(teacher_id, DONE_MIN_EVIDENCE)
        ordered = personalise.order_path(entries, ctx.class_struggles, done_moves=frozenset(done))
        if [(e.move_id, e.reason) for e in ordered] != [(e.move_id, e.reason) for e in entries]:
            await self.repo.replace_move_path(teacher_id, ordered)

    async def set_class_struggles(self, teacher_id: UUID, ids: list[str]) -> list[str]:
        """The "My class" page saved (or cleared) her choice: closed list, ordered, at most 3."""
        ctx = await self.get_or_create_context(teacher_id)
        ctx.class_struggles = class_flow.clean_ids(ids)
        ctx.class_stage = class_flow.STAGE_NONE
        ctx.class_pending = []
        await self._after_class_saved(ctx, teacher_id)
        await self._sync_context_to_db(ctx, teacher_id)
        return list(ctx.class_struggles)

    async def start_class_profile(self, teacher_id: UUID) -> list[OutboundMessage]:
        """Teacher home -> chat: ask where her class is struggling (voice, text or a number)."""
        ctx = await self.get_or_create_context(teacher_id)
        result = class_flow.start(ctx)
        await self._sync_context_to_db(ctx, teacher_id)
        return result.messages

    async def handle_inbound(self, inbound: InboundMessage) -> list[OutboundMessage]:
        """Handles one teacher message, then records which module steps it completed."""
        out = await self._handle_inbound(inbound)
        try:
            await self._track_module_progress(inbound.teacher_id)
        except SQLAlchemyError:
            logger.warning("module progress tracking failed", exc_info=True)
        return out

    async def _track_module_progress(self, teacher_id: UUID) -> None:
        """Derives module step completion from where the weekly loop now is (never undone)."""
        ctx = await self.get_or_create_context(teacher_id)
        if ctx.onboarding_state != OnboardingStateEnum.READY:
            return
        module_id = ctx.current_move_id
        if module_id not in modules.module_ids():
            return
        learned = ctx.current_state not in (
            SessionStateEnum.LEARN,
            SessionStateEnum.EXPLAIN_BACK,
            SessionStateEnum.ASK,
        )
        if learned:
            await self.repo.mark_module_step(teacher_id, module_id, modules.STEP_LEARN)
        if ctx.rehearse_mode == rehearse_setup.MODE_ONE_ON_ONE and ctx.diagnosis:
            verdict = "skipped" if ctx.diagnosis.get("skipped") else ctx.diagnosis.get("verdict")
            await self.repo.mark_module_step(
                teacher_id, module_id, modules.STEP_DIAGNOSE, verdict=verdict
            )
            if ctx.current_state in (
                SessionStateEnum.FEEDBACK,
                SessionStateEnum.TRY_IN_CLASS,
                SessionStateEnum.REFLECT_PEER,
                SessionStateEnum.REFLECT_SELF,
                SessionStateEnum.DONE,
            ):
                await self.repo.mark_module_step(teacher_id, module_id, modules.STEP_PRACTISE)

    async def start_module(self, teacher_id: UUID, module_id: str) -> list[OutboundMessage]:
        """Picker to chat: restart the weekly loop on this module (learn step first)."""
        if module_id not in modules.module_ids():
            raise ValueError(f"unknown module: {module_id}")
        ctx = await self.get_or_create_context(teacher_id)
        address_form = ctx.address_form
        ctx.current_move_id = module_id
        ctx.current_state = SessionStateEnum.LEARN
        ctx.rehearsal_turns_count = 0
        ctx.retries_count = 0
        ctx.rating_stage = ""
        ctx.rehearse_stage = rehearse_setup.STAGE_NONE
        ctx.rehearse_mode = ""
        ctx.rehearse_child = ""
        ctx.diagnosis = {}
        ctx.module_mode = True
        ctx.module_check_stage = modules.CHECK_IDLE
        await self._sync_context_to_db(ctx, teacher_id)
        move = load_move_card(module_id)
        intro_text, intro_cites = await self._learn_intro(move, address_form, ctx.class_struggles)
        return [
            OutboundMessage(
                kind="text",
                text_hi=intro_text,
                citations=intro_cites,
                buttons=[
                    Button(
                        id="btn_understood", title_hi=get_message("btn_understood", address_form)
                    ),
                    Button(id="btn_replay", title_hi=get_message("btn_replay", address_form)),
                ],
            )
        ]

    async def _handle_inbound(self, inbound: InboundMessage) -> list[OutboundMessage]:
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
                move = load_move_card(ctx.current_move_id)
                intro_text, intro_cites = await self._learn_intro(
                    move, address_form, ctx.class_struggles
                )
                return [
                    OutboundMessage(
                        kind="text",
                        text_hi=intro_text,
                        citations=intro_cites,
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

        # 1b. "Rate the training" (after REFLECT): the rating and the one-line comment are free
        # answers, so they are read here before intent routing can mistake them for commands.
        if (
            ctx.rating_stage
            and ctx.current_state == SessionStateEnum.DONE
            and matched_intent != Intent.DELETE
            and text_content != "delete"
        ):
            if is_rating_escape(matched_intent, text_content):
                # A known command (menu, next, progress, language...) ends the rating prompt
                # without storing anything and is processed normally below.
                await self._clear_rating_stage(ctx, teacher_id)
            else:
                return await self._handle_training_rating(ctx, teacher_id, text_content, btn_id)

        # 1c. "My class" (optional): her words about where the class struggles, or a chip number
        if (
            ctx.onboarding_state == OnboardingStateEnum.READY
            and matched_intent != Intent.DELETE
            and text_content != "delete"
            and not ctx.awaiting_delete_confirm
        ):
            stage_before = ctx.class_stage
            class_res = await class_flow.handle(ctx, text_content, btn_id, matched_intent)
            if class_res.handled:
                if class_res.saved:
                    await self._after_class_saved(ctx, teacher_id)
                await self._sync_context_to_db(ctx, teacher_id)
                return class_res.messages
            if ctx.class_stage != stage_before:
                await self._sync_context_to_db(ctx, teacher_id)

        # 2. Delete confirmation flow (§8.3 step 7)
        if ctx.awaiting_delete_confirm:
            if (
                matched_intent in (Intent.CONFIRM_DELETE, Intent.CONFIRM_YES)
                or btn_id == "btn_delete_confirm"
                or text_content == "confirm_delete"
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
                move = load_move_card(ctx.current_move_id)
                if prompt_key == "learn_intro":
                    prompt_msg = get_message(prompt_key, address_form, move_title=move.title_hi)
                elif prompt_key == "rehearse_intro":
                    prompt_msg = get_message(
                        prompt_key, address_form, scene_intro=move.scenario.intro_hi
                    )
                else:
                    prompt_msg = get_message(prompt_key, address_form)
                return [
                    OutboundMessage(
                        kind="text",
                        text_hi=prompt_msg,
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
                        Button(
                            id="btn_delete_confirm",
                            title_hi=get_message("btn_yes", address_form),
                        ),
                        Button(
                            id="btn_delete_cancel",
                            title_hi=get_message("btn_no", address_form),
                        ),
                    ],
                )
            ]

        # 3. ASK interrupt flow (§8.3 step 5, §8.4) & Admin escalation (Requirement B.7)
        is_ask_keyword = matched_intent in (
            Intent.ASK,
            Intent.ADMIN,
        ) or text_content.lower().startswith(("question", "sawal"))
        if is_ask_keyword or ctx.current_state == SessionStateEnum.ASK:
            if ctx.current_state != SessionStateEnum.ASK:
                ctx.prior_state_before_ask = ctx.current_state
                ctx.current_state = SessionStateEnum.ASK

            q_text = extract_ask_query(text_content) if is_ask_keyword else text_content
            if matched_intent == Intent.ADMIN:
                if not q_text:
                    q_text = text_content
                q_rec = await self.repo.record_question(
                    teacher_id=teacher_id,
                    text=q_text,
                    category="admin",
                    answer_hi=get_message("ask_admin", address_form),
                    source_ids=[],
                    confidence=1.0,
                    status="escalated",
                )
                await self.repo.record_review_item(
                    kind="question",
                    ref_id=str(q_rec.id),
                    reason="Admin escalation",
                )
                reply_text = get_message("ask_admin", address_form)

                prior = ctx.prior_state_before_ask or SessionStateEnum.LEARN
                ctx.current_state = prior
                ctx.prior_state_before_ask = None
                ctx.clarifying_already_asked = False
                await self._sync_context_to_db(ctx, teacher_id)

                resume_note = get_message("ask_resume", address_form)
                prior_prompt = self._get_resume_prompt(ctx, prior, address_form)

                return [
                    OutboundMessage(kind="text", text_hi=reply_text),
                    OutboundMessage(kind="text", text_hi=f"{resume_note}\n\n{prior_prompt}"),
                ]

            if not q_text:
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
            chunks = await self.retriever.retrieve_supported(
                classify_res.output.search_query_hi or q_text
            )
            schema_chunks = [
                RetrievedChunk(
                    chunk_id=c.chunk_id,
                    source_short_hi=getattr(c, "source_short_hi", None) or c.source,
                    section=c.section,
                    page=c.page,
                    text=c.text,
                    gloss_hi=c.gloss_hi,
                    keywords_hi=c.keywords_hi,
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
            q_rec = await self.repo.record_question(
                teacher_id=teacher_id,
                text=q_text,
                category=classify_res.output.category,
                answer_hi=answer_res.output.answer_hi,
                source_ids=answer_res.output.source_ids,
                confidence=answer_res.output.confidence,
                status=status_val,
            )
            if status_val == "escalated":
                await self.repo.record_review_item(
                    kind="question",
                    ref_id=str(q_rec.id),
                    reason=f"Question escalated: {classify_res.output.category}",
                )

            # Compose reply
            if answer_res.escalated:
                if classify_res.output.category == "admin":
                    reply_key = "ask_admin"
                elif answer_res.no_sources:
                    reply_key = "ask_not_in_sources"
                else:
                    reply_key = "ask_escalated"
                reply_text = get_message(reply_key, address_form)
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
            prior_prompt = self._get_resume_prompt(ctx, prior, address_form)

            return [
                OutboundMessage(
                    kind="text",
                    text_hi=reply_text,
                    # A generated guide answer gets the "guide" speaker (the web UI offers a
                    # translation for it); escalation / canned replies are plain system text.
                    speaker=None if answer_res.escalated else "guide",
                    citations=[]
                    if answer_res.escalated
                    else citations_for_chunks(answer_res.sources_cited, address_form),
                ),
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
                # Any other input before consent: welcome + consent prompt (spec/08 §8.1 NEW row).
                # Without this, a NEW teacher fell through to the weekly loop and got 'unclear'.
                return [
                    OutboundMessage(kind="text", text_hi=get_message("welcome", address_form)),
                    OutboundMessage(
                        kind="buttons",
                        text_hi=get_message("consent_service", address_form),
                        buttons=[
                            Button(id="btn_agree", title_hi=get_message("btn_agree", address_form)),
                            Button(id="btn_more", title_hi=get_message("btn_more", address_form)),
                            Button(
                                id="btn_decline",
                                title_hi=get_message("btn_decline", address_form),
                            ),
                        ],
                    ),
                ]

            elif current_onboarding == OnboardingStateEnum.JOIN_CODE:
                if (
                    matched_intent == Intent.CONFIRM_NO
                    or text_content in ("no_code", "skip")
                    or btn_id in ("btn_no", "btn_skip")
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
                            Button(
                                id="btn_female",
                                title_hi=get_message("btn_female", address_form),
                            ),
                            Button(
                                id="btn_male",
                                title_hi=get_message("btn_male", address_form),
                            ),
                        ],
                    )
                ]

            elif current_onboarding == OnboardingStateEnum.PROFILE_ADDRESS:
                osm.transition(btn_id or text_content)
                await self._sync_context_to_db(ctx, teacher_id)
                default_name = (
                    get_message("btn_female", ctx.address_form)
                    if ctx.address_form == "f"
                    else get_message("btn_male", ctx.address_form)
                )
                return [
                    OutboundMessage(
                        kind="text",
                        text_hi=get_message(
                            "ask_experience", ctx.address_form, name=ctx.name or default_name
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
                            Button(
                                id="btn_yes",
                                title_hi=get_message("btn_yes", ctx.address_form),
                            ),
                            Button(
                                id="btn_no",
                                title_hi=get_message("btn_no", ctx.address_form),
                            ),
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
                # Initialize placement scene with Ravi on 52-17
                scene = await scene_store.get_active_for_teacher(teacher_id)
                if scene is None:
                    ravi = ChildRuntime(
                        persona_id="ravi",
                        misconception="SUB_SMALLER_FROM_LARGER",
                        temperament="confident",
                        state=ChildState.MISCONCEPTION,
                    )
                    scene = await self.scene_runner.create_scene(
                        teacher_id=teacher_id,
                        move_id="NUM_SUB_REGROUP_BUNDLES",
                        item=Problem(type="sub", a=52, b=17),
                        children=[ravi],
                    )
                turn_res = None
                if scene is not None:
                    turn_res = await self.scene_runner.turn(
                        scene_id=scene.scene_id,
                        transcript=text_content,
                        address_form=ctx.address_form,
                    )
                await self._sync_context_to_db(ctx, teacher_id)
                return turn_res.outbound if turn_res else []

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
                    placement_used_tell_answer = False
                    if scene is not None:
                        for t in scene.turns:
                            if (
                                TeachingAct.TELL_ANSWER.value in t.acts
                                or TeachingAct.TELL_ANSWER in t.acts
                            ):
                                placement_used_tell_answer = True
                                break

                    path_entries = compute_move_path(
                        teacher_id=teacher_id,
                        first_year=ctx.first_year,
                        classes=ctx.classes,
                        placement_used_tell_answer=placement_used_tell_answer,
                    )
                    await self.repo.record_move_path(teacher_id, path_entries)
                    if path_entries:
                        ctx.current_move_id = path_entries[0].move_id
                    ctx.current_state = SessionStateEnum.LEARN
                    await self._sync_context_to_db(ctx, teacher_id)

                    first_move = load_move_card(ctx.current_move_id)
                    ready_outbounds: list[OutboundMessage] = []
                    first_text, first_cites = await self._learn_intro(
                        first_move, ctx.address_form, ctx.class_struggles
                    )
                    if turn_res:
                        ready_outbounds.extend(turn_res.outbound)
                    ready_outbounds.extend(
                        [
                            OutboundMessage(
                                kind="text",
                                text_hi=get_message("placement_done", ctx.address_form),
                            ),
                            OutboundMessage(
                                kind="text",
                                text_hi=get_message(
                                    "ready_first_move",
                                    ctx.address_form,
                                    move_title=first_move.title_hi,
                                ),
                            ),
                            OutboundMessage(
                                kind="buttons",
                                text_hi=first_text,
                                citations=first_cites,
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
                    if not ctx.class_struggles:
                        ready_outbounds.append(class_flow.invite_message())
                        teacher_row = await self.repo.get_or_create_teacher(teacher_id)
                        teacher_row.class_profile_prompted_at = now
                    return ready_outbounds

                await self._sync_context_to_db(ctx, teacher_id)
                return turn_res.outbound if turn_res else []

        # 5. Weekly Loop Flow (§8.2)
        wsm = WeeklyStateMachine(ctx)
        curr = ctx.current_state

        if curr == SessionStateEnum.LEARN:
            move = load_move_card(ctx.current_move_id)
            if matched_intent == Intent.REPEAT or btn_id == "btn_replay":
                intro_text, intro_cites = await self._learn_intro(
                    move, address_form, ctx.class_struggles
                )
                return [
                    OutboundMessage(
                        kind="buttons",
                        text_hi=intro_text,
                        citations=intro_cites,
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
            # Free text does NOT silently advance (§8.3 step 4); remind of the two buttons
            return [
                OutboundMessage(
                    kind="buttons",
                    text_hi=get_message(
                        "learn_buttons_reminder",
                        address_form,
                        next=get_message("btn_understood", address_form),
                        replay=get_message("btn_replay", address_form),
                    ),
                    buttons=[
                        Button(
                            id="btn_understood",
                            title_hi=get_message("btn_understood", address_form),
                        ),
                        Button(id="btn_replay", title_hi=get_message("btn_replay", address_form)),
                    ],
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
            except (LLMUnavailable, TimeoutError, ValueError, TypeError) as exc:
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
            move = load_move_card(ctx.current_move_id)
            if matched_intent == Intent.LISTEN or btn_id == "btn_listen":
                wsm.transition("btn_listen")
                await self._sync_context_to_db(ctx, teacher_id)
                model_lines = [t.text_hi for t in move.model_rehearsal if t.text_hi]
                model_text = (
                    "\n\n".join(model_lines)
                    if model_lines
                    else get_message("model_header", address_form)
                )
                return [
                    OutboundMessage(kind="text", text_hi=get_message("model_header", address_form)),
                    OutboundMessage(kind="text", text_hi=model_text),
                    *await self._begin_rehearse_setup(ctx, teacher_id, move),
                ]
            if matched_intent == Intent.SKIP or btn_id == "btn_skip":
                wsm.transition("btn_skip")
                await self._sync_context_to_db(ctx, teacher_id)
                return await self._begin_rehearse_setup(ctx, teacher_id, move)
            # Free text does NOT silently advance
            return [
                OutboundMessage(
                    kind="text",
                    text_hi=get_message("unclear", address_form),
                )
            ]

        elif curr == SessionStateEnum.REHEARSE_INTRO:
            if ctx.rehearse_stage in rehearse_setup.SETUP_STAGES:
                setup_messages = await rehearse_setup.handle_setup(
                    ctx=ctx,
                    teacher_id=teacher_id,
                    move=load_move_card(ctx.current_move_id),
                    runner=self.scene_runner,
                    store=scene_store,
                    matched_intent=matched_intent,
                    btn_id=btn_id,
                    text=text_content,
                )
                await self._sync_context_to_db(ctx, teacher_id)
                return setup_messages
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

            early_text_rows: list[Message] = []

            async def _on_text_ready(
                child_lines: list[ChildLineRecord], text_msgs: list[OutboundMessage]
            ) -> None:
                if inbound.channel == "web":
                    for tm in text_msgs:
                        row_id = uuid.uuid4()
                        tm.message_id = row_id
                        db_msg = Message(
                            id=row_id,
                            teacher_id=teacher_id,
                            direction="out",
                            channel="web",
                            channel_msg_id=str(uuid.uuid4()),
                            kind="text",
                            text=unicodedata.normalize("NFC", tm.text_hi) if tm.text_hi else None,
                            audio_ref=None,
                            buttons=[b.model_dump() for b in tm.buttons] if tm.buttons else None,
                            speaker=tm.speaker,
                            template_name=tm.template_name,
                            created_at=datetime.now(UTC),
                        )
                        self.repo.session.add(db_msg)
                        early_text_rows.append(db_msg)
                    await self.repo.session.commit()

            turn_res = await self.scene_runner.turn(
                scene_id=scene.scene_id,
                transcript=text_content,
                address_form=address_form,
                on_text_ready=_on_text_ready,
            )

            if early_text_rows:
                for outbound in turn_res.outbound:
                    for early_row in early_text_rows:
                        if (
                            early_row.speaker == outbound.speaker
                            and early_row.text == outbound.text_hi
                        ):
                            if outbound.audio_ref:
                                early_row.audio_ref = outbound.audio_ref
                                early_row.kind = "audio"
                                now_utc = datetime.now(UTC)
                                if now_utc <= early_row.created_at:
                                    now_utc = early_row.created_at + timedelta(milliseconds=1)
                                early_row.updated_at = now_utc
                            outbound.already_persisted = True
                await self.repo.session.commit()

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

                teacher_turns = [t for t in scene.turns if t.transcript and t.acts != ["stop"]]
                teacher_turns_count = len(teacher_turns)

                trajectories: dict[str, list[ChildState]] = {}
                for child in scene.scene_state.children:
                    if child.history:
                        trajectories[child.persona_id] = [ChildState.MISCONCEPTION] + [
                            h[1] for h in child.history
                        ]
                    else:
                        trajectories[child.persona_id] = [child.state]

                min_turns = (
                    settings.MIN_TURNS_FOR_COACH_ONE_ON_ONE
                    if scene.scene_state.one_on_one
                    else settings.MIN_TURNS_FOR_COACH_GROUP
                )
                # Too short for useful feedback: say so and let the teacher continue or skip
                if not scene.turns or teacher_turns_count < min_turns or not trajectories:
                    ctx.resume_scene_id = str(scene.scene_id)
                    await self._sync_context_to_db(ctx, teacher_id)
                    needed_more = max(1, min_turns - teacher_turns_count)
                    neutral = get_message("scene_ended_neutral", address_form)
                    return [
                        *[m for m in turn_res.outbound if m.text_hi != neutral],
                        OutboundMessage(
                            kind="buttons",
                            text_hi=get_message(
                                "scene_too_short",
                                address_form,
                                done=teacher_turns_count,
                                needed=min_turns,
                                more=needed_more,
                            ),
                            buttons=[
                                Button(
                                    id="btn_scene_continue",
                                    title_hi=get_message("btn_scene_continue", address_form),
                                ),
                                Button(
                                    id="btn_skip",
                                    title_hi=get_message("btn_skip", address_form),
                                ),
                            ],
                        ),
                    ]

                # Generate coach feedback (one-on-one: its own rubric, plus the diagnosis result)
                move = load_move_card(ctx.current_move_id)
                one_on_one = scene.scene_state.one_on_one
                diagnosis_result: DiagnosisResult | None = None
                diagnosis_skipped = False
                if one_on_one and ctx.diagnosis:
                    diagnosis_skipped = bool(ctx.diagnosis.get("skipped"))
                    diagnosis_result = DiagnosisResult.model_validate(
                        {k: v for k, v in ctx.diagnosis.items() if k != "skipped"}
                    )
                coach_move = move.one_on_one_view() if one_on_one else move
                # 1. turns: all scene turns in chronological order (teacher + child responses)
                all_scene_turns: list[SceneTurn] = []
                # 2. acts: actual tagged acts for each teacher turn with NO fallback to [REPEAT_QUESTION]!
                tagged_acts: list[list[TeachingAct]] = []

                for t in scene.turns:
                    if t.transcript and t.acts != ["stop"]:
                        all_scene_turns.append(SceneTurn(speaker="teacher", text_hi=t.transcript))
                        turn_acts = [
                            TeachingAct(a) for a in t.acts if a in TeachingAct._value2member_map_
                        ]
                        tagged_acts.append(turn_acts)
                    if t.child_lines:
                        for cl in t.child_lines:
                            line_text = getattr(cl, "line_hi", None) or getattr(cl, "text_hi", "")
                            if line_text:
                                all_scene_turns.append(
                                    SceneTurn(speaker=cl.persona_id, text_hi=line_text)
                                )
                    elif t.child_responses:
                        for cr in t.child_responses:
                            resp_text = str(cr.answer) if cr.answer is not None else ""
                            if resp_text:
                                all_scene_turns.append(
                                    SceneTurn(speaker=cr.persona_id, text_hi=resp_text)
                                )

                # target_child_id: find target child with misconception
                target_child_id = next(
                    (c.persona_id for c in scene.scene_state.children if c.misconception),
                    scene.scene_state.children[0].persona_id
                    if scene.scene_state.children
                    else "ravi",
                )

                # 3. current_item_answer from scene.scene_state.current_item.answer()
                current_item_answer = scene.scene_state.current_item.answer()

                try:
                    coach_res = await coach_feedback(
                        move=coach_move,
                        turns=all_scene_turns,
                        acts=tagged_acts,
                        trajectories=trajectories,
                        target_child_id=target_child_id,
                        current_item_answer=current_item_answer,
                        attempt=ctx.retries_count + 1,
                        diagnosis=diagnosis_result,
                        diagnosis_skipped=diagnosis_skipped,
                        one_on_one=one_on_one,
                    )
                except (LLMUnavailable, TimeoutError, ValueError, TypeError) as exc:
                    logger.warning("Coach feedback failed: %s; using deterministic fallback", exc)
                    from backend.app.llm.roles.coach import CoachResult, fallback_coach_feedback

                    coach_fb = fallback_coach_feedback(
                        move=coach_move,
                        turns=all_scene_turns,
                        acts=tagged_acts,
                        trajectories=trajectories,
                        target_child_id=target_child_id,
                        current_item_answer=current_item_answer,
                        attempt=ctx.retries_count + 1,
                        reason=f"coach_error:{type(exc).__name__}",
                        diagnosis=diagnosis_result,
                        diagnosis_skipped=diagnosis_skipped,
                        one_on_one=one_on_one,
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
                    evidence=(
                        {
                            "mode": "one_on_one",
                            "diagnosis_verdict": (
                                "skipped" if diagnosis_skipped else diagnosis_result.verdict.value
                            )
                            if diagnosis_result
                            else None,
                        }
                        if one_on_one
                        else {}
                    ),
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

                ctx.rehearse_stage = rehearse_setup.STAGE_NONE
                await self._sync_context_to_db(ctx, teacher_id)
                suggestion = await self._source_suggestion(
                    move, coach_res.feedback.change_hi, address_form
                )
                suggestion_msgs = [suggestion] if suggestion else []
                class_focus = personalise.focus_child(move, ctx.class_struggles)
                if class_focus is not None:
                    suggestion_msgs.insert(
                        0,
                        OutboundMessage(
                            kind="text",
                            text_hi=get_message(
                                "coach_class_link",
                                address_form,
                                label=personalise.label_of(class_focus.struggle),
                                child=rehearse_setup.child_name(class_focus.persona_id),
                            ),
                        ),
                    )
                coach_outbounds: list[OutboundMessage] = list(turn_res.outbound)
                coach_outbounds.extend(
                    [
                        OutboundMessage(
                            kind="text", text_hi=get_message("feedback_header", address_form)
                        ),
                        OutboundMessage(kind="text", text_hi=f"{prefix}{feedback_body}"),
                        *suggestion_msgs,
                        OutboundMessage(
                            kind="buttons",
                            text_hi=self._realism_prompt(ctx, address_form),
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
            move = load_move_card(ctx.current_move_id)
            if ctx.resume_scene_id and (btn_id == "btn_scene_continue"):
                resumed = await self._resume_scene(ctx, teacher_id)
                if resumed:
                    return [
                        OutboundMessage(
                            kind="text", text_hi=get_message("scene_resumed", address_form)
                        )
                    ]
                ctx.current_state = SessionStateEnum.REHEARSE_INTRO
                ctx.resume_scene_id = ""
                return await self._begin_rehearse_setup(ctx, teacher_id, move)
            if ctx.resume_scene_id and (btn_id == "btn_skip" or matched_intent == Intent.SKIP):
                btn_id = "btn_continue"  # skipping the too-short scene's feedback moves on
                matched_intent = Intent.NEXT
            ctx.resume_scene_id = ""
            if ctx.module_mode and ctx.module_check_stage == modules.CHECK_ASKING:
                if matched_intent == Intent.NEXT or btn_id == "btn_continue":
                    ctx.module_check_stage = modules.CHECK_DONE  # skipped: the module stays open
                    await self._sync_context_to_db(ctx, teacher_id)
                elif matched_intent != Intent.RETRY and btn_id != "btn_retry" and text_content:
                    check = await check_module(
                        move,
                        text_content,
                        get_message("module_check_prompt", address_form, move_title=move.title_hi),
                        address_form,
                    )
                    await self.repo.mark_module_step(
                        teacher_id,
                        ctx.current_move_id,
                        modules.STEP_CHECK,
                        passed=check.passed,
                        covered=check.covered,
                    )
                    ctx.module_check_stage = modules.CHECK_DONE
                    await self._sync_context_to_db(ctx, teacher_id)
                    done_key = (
                        "module_check_done_pass" if check.passed else "module_check_done_more"
                    )
                    return [
                        OutboundMessage(kind="text", text_hi=check.reply_hi, speaker="coach"),
                        OutboundMessage(
                            kind="buttons",
                            text_hi=get_message(done_key, address_form),
                            buttons=[
                                Button(
                                    id="btn_continue",
                                    title_hi=get_message("btn_continue", address_form),
                                )
                            ],
                        ),
                    ]
            if matched_intent == Intent.RETRY or btn_id == "btn_retry":
                res = wsm.transition("btn_retry")
                await self._sync_context_to_db(ctx, teacher_id)
                if res.new_state == "REHEARSE_INTRO":
                    return await self._begin_rehearse_setup(ctx, teacher_id, move)
                if self.repo.session is not None:
                    try:
                        from backend.app.jobs.handlers import schedule_followup_try_in_class

                        async with self.repo.session.begin_nested():
                            await schedule_followup_try_in_class(
                                self.repo.session, teacher_id, ctx.current_move_id, now=now
                            )
                    except (SQLAlchemyError, ValueError):
                        logger.warning("Could not schedule followup_try_in_class", exc_info=True)

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
            if (
                (matched_intent == Intent.NEXT or btn_id == "btn_continue")
                and ctx.module_mode
                and ctx.module_check_stage == modules.CHECK_IDLE
            ):
                # Module closing check: one question in the teacher's own words, then the loop goes on
                ctx.module_check_stage = modules.CHECK_ASKING
                await self._sync_context_to_db(ctx, teacher_id)
                return [
                    OutboundMessage(
                        kind="text",
                        text_hi=get_message(
                            "module_check_prompt", address_form, move_title=move.title_hi
                        ),
                    )
                ]
            if matched_intent == Intent.NEXT or btn_id == "btn_continue":
                wsm.transition("btn_continue")
                await self._sync_context_to_db(ctx, teacher_id)
                if self.repo.session is not None:
                    try:
                        from backend.app.jobs.handlers import schedule_followup_try_in_class

                        async with self.repo.session.begin_nested():
                            await schedule_followup_try_in_class(
                                self.repo.session, teacher_id, ctx.current_move_id, now=now
                            )
                    except (SQLAlchemyError, ValueError):
                        logger.warning("Could not schedule followup_try_in_class", exc_info=True)

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

            # Realism rating handling (1 to 5)
            rating_val: int | None = None
            if btn_id and btn_id.startswith("btn_rating_"):
                try:
                    rating_val = int(btn_id.split("_")[-1])
                except ValueError:
                    rating_val = None
            elif text_content:
                for tok in text_content.split():
                    try:
                        v = int(tok)
                        if 1 <= v <= 5:
                            rating_val = v
                            break
                    except ValueError:
                        continue

            if rating_val is not None and 1 <= rating_val <= 5:
                scene = await scene_store.get_active_for_teacher(teacher_id)
                scene_id = scene.scene_id if scene else None
                await self.repo.record_realism_rating(
                    teacher_id=teacher_id, rating=rating_val, scene_id=scene_id
                )
                await self._sync_context_to_db(ctx, teacher_id)
                return [
                    OutboundMessage(
                        kind="buttons",
                        text_hi=self._realism_prompt(ctx, address_form),
                        buttons=[
                            Button(id="btn_retry", title_hi=get_message("btn_retry", address_form)),
                            Button(
                                id="btn_continue",
                                title_hi=get_message("btn_continue", address_form),
                            ),
                        ],
                    )
                ]

            # Any other text -> send unclear + retry/continue buttons; never send an empty reply!
            return [
                OutboundMessage(
                    kind="buttons",
                    text_hi=get_message("unclear", address_form),
                    buttons=[
                        Button(id="btn_retry", title_hi=get_message("btn_retry", address_form)),
                        Button(
                            id="btn_continue",
                            title_hi=get_message("btn_continue", address_form),
                        ),
                    ],
                )
            ]

        elif curr == SessionStateEnum.TRY_IN_CLASS:
            move = load_move_card(ctx.current_move_id)
            if matched_intent == Intent.PEER or btn_id == "btn_peer":
                wsm.transition("btn_peer")
                await self._sync_context_to_db(ctx, teacher_id)
                item_text = move.peer_checklist[0] if move.peer_checklist else ""
                total_items = len(move.peer_checklist) if move.peer_checklist else 3
                return [
                    OutboundMessage(
                        kind="buttons",
                        text_hi=get_message(
                            "peer_item",
                            address_form,
                            i=1,
                            n=total_items,
                            item=item_text,
                        ),
                        buttons=[
                            Button(id="btn_yes", title_hi=get_message("btn_yes", address_form)),
                            Button(id="btn_no", title_hi=get_message("btn_no", address_form)),
                        ],
                    )
                ]
            if matched_intent == Intent.SELF or btn_id == "btn_self":
                wsm.transition("btn_self")
                await self._sync_context_to_db(ctx, teacher_id)
                q_text = move.reflection_questions[0] if move.reflection_questions else ""
                return [
                    OutboundMessage(
                        kind="text",
                        text_hi=get_message(
                            "reflect_q",
                            address_form,
                            i=1,
                            question=q_text,
                        ),
                    )
                ]
            if matched_intent == Intent.LATER or btn_id == "btn_later":
                wsm.transition("btn_later")
                await self._sync_context_to_db(ctx, teacher_id)
                default_name = (
                    get_message("btn_female", address_form)
                    if address_form == "f"
                    else get_message("btn_male", address_form)
                )
                return [
                    OutboundMessage(
                        kind="text",
                        text_hi=get_message(
                            "reminder", address_form, name=ctx.name or default_name
                        ),
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
            move = load_move_card(ctx.current_move_id)
            res = wsm.transition(text_content)
            if res.new_state == "DONE":
                await self.repo.record_adoption_evidence(
                    teacher_id=teacher_id,
                    move_id=ctx.current_move_id,
                    level=3,
                    source="peer_checklist",
                )
                await self._sync_context_to_db(ctx, teacher_id)
                return await self._begin_training_rating(ctx, teacher_id, 3)
            await self._sync_context_to_db(ctx, teacher_id)
            step_idx = max(0, ctx.reflect_step - 1)
            item_text = move.peer_checklist[step_idx] if step_idx < len(move.peer_checklist) else ""
            total_items = len(move.peer_checklist) if move.peer_checklist else 3
            return [
                OutboundMessage(
                    kind="buttons",
                    text_hi=get_message(
                        "peer_item",
                        address_form,
                        i=ctx.reflect_step,
                        n=total_items,
                        item=item_text,
                    ),
                    buttons=[
                        Button(id="btn_yes", title_hi=get_message("btn_yes", address_form)),
                        Button(id="btn_no", title_hi=get_message("btn_no", address_form)),
                    ],
                )
            ]

        elif curr == SessionStateEnum.REFLECT_SELF:
            move = load_move_card(ctx.current_move_id)
            res = wsm.transition(text_content)
            if res.new_state == "DONE":
                await self.repo.record_adoption_evidence(
                    teacher_id=teacher_id,
                    move_id=ctx.current_move_id,
                    level=2,
                    source="reflection",
                )
                await self._sync_context_to_db(ctx, teacher_id)
                return await self._begin_training_rating(ctx, teacher_id, 2)
            await self._sync_context_to_db(ctx, teacher_id)
            step_idx = max(0, ctx.reflect_step - 1)
            q_text = (
                move.reflection_questions[step_idx]
                if step_idx < len(move.reflection_questions)
                else ""
            )
            return [
                OutboundMessage(
                    kind="text",
                    text_hi=get_message(
                        "reflect_q", address_form, i=ctx.reflect_step, question=q_text
                    ),
                )
            ]

        elif curr == SessionStateEnum.DONE:
            move = load_move_card(ctx.current_move_id)
            if matched_intent == Intent.NEXT or btn_id == "btn_next_move":
                wsm.transition("btn_next_move")
                await self._sync_context_to_db(ctx, teacher_id)
                intro_text, intro_cites = await self._learn_intro(
                    move, address_form, ctx.class_struggles
                )
                return [
                    OutboundMessage(
                        kind="buttons",
                        text_hi=intro_text,
                        citations=intro_cites,
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
                            "progress_summary",
                            address_form,
                            n_done=1,
                            lines=f"1. {move.title_hi}",
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
