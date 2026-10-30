"""The follow-up loop: "How did yesterday's practice go?" (flag FOLLOWUP_ENABLED).

After a check-in with a struggle, one follow-up is stored with a due date (the next school day,
Monday to Saturday). The next time she opens the chat on or after that day the chat offers three
closed options (worked / still stuck / could not try); "could not try" asks why with four closed
options. Every reply is deterministic: a stored tip with its handbook citations, a line pointing to
the level sorter or the handbook, or the next move in her path. No free text, no child data, no LLM.

The date logic and the replies are pure functions of their inputs, so tests fix the clock.
`tomorrow_focus` is the builder for an opt-in weekly note; nothing calls it yet (see docs/ux/V3_LOG.md
for how the WhatsApp channel would).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from backend.app.class_profile import level_sorter
from backend.app.class_profile.checkin_flow import _source_lines, struggle_label
from backend.app.class_profile.library import ClassStruggle, StruggleLibrary, load_library
from backend.app.config import settings, v2_enabled
from backend.app.core.messages import get_message, get_ui_lang, has_message
from backend.app.core.types import Button, Citation, OutboundMessage
from backend.app.sessions.state_machine import SessionContext
from backend.app.sessions.titles import move_title

IST = ZoneInfo("Asia/Kolkata")

STAGE_NONE = ""
STAGE_ASK = "ask"  # the three options are on screen
STAGE_WHY = "why"  # "could not try": waiting for the reason

OUTCOME_WORKED = "worked"
OUTCOME_STUCK = "stuck"
OUTCOME_CANT = "cant"
OUTCOMES = (OUTCOME_WORKED, OUTCOME_STUCK, OUTCOME_CANT)
REASONS = ("time", "multigrade", "absent", "other")

BTN_WORKED = "btn_fu_worked"
BTN_STUCK = "btn_fu_stuck"
BTN_CANT = "btn_fu_cant"
BTN_PRACTICE = "btn_fu_practice"
BTN_HANDBOOK = "btn_fu_handbook"
BTN_BACK = "btn_fu_back"  # "Back to practice": returns to the open scene
WHY_PREFIX = "btn_fu_why_"
OUTCOME_BUTTONS = {BTN_WORKED: OUTCOME_WORKED, BTN_STUCK: OUTCOME_STUCK, BTN_CANT: OUTCOME_CANT}
WHY_BUTTONS = {f"{WHY_PREFIX}{r}": r for r in REASONS}
ALL_BUTTONS = frozenset({*OUTCOME_BUTTONS, *WHY_BUTTONS, BTN_PRACTICE, BTN_HANDBOOK, BTN_BACK})
LEADIN_OUTCOME_KEYS = {"well": "fu_leadin_well", "some": "fu_leadin_some", "most": "fu_leadin_most"}


def enabled() -> bool:
    return v2_enabled(settings.FOLLOWUP_ENABLED)


def utcnow() -> datetime:
    """The clock every follow-up decision reads (tests replace this one function)."""
    return datetime.now(UTC)


def ist_date(moment: datetime) -> date:
    return moment.astimezone(IST).date()


def next_school_day(day: date) -> date:
    """The first school day (Monday to Saturday) after `day`; a Saturday or Sunday gives Monday."""
    nxt = day + timedelta(days=1)
    while nxt.weekday() not in settings.FOLLOWUP_SCHOOL_DAYS:
        nxt += timedelta(days=1)
    return nxt


def due_date_for(checkin_at: datetime) -> date:
    return next_school_day(ist_date(checkin_at))


def is_due(due: date, today: date) -> bool:
    return today >= due


def _btn(button_id: str) -> Button:
    return Button(id=button_id, title_hi=get_message(button_id)[: settings.WEB_BUTTON_TITLE_MAX])


def ask_message(
    struggle: ClassStruggle | None,
    *,
    module_id: str | None = None,
    checkin_outcome: str | None = None,
) -> OutboundMessage:
    """The three options, led in by what she told us after class (module and outcome) when stored."""
    label = struggle_label(struggle) if struggle is not None else get_message("fu_unknown_label")
    module_key = f"btn_chk_mod_{module_id}"
    outcome_key = LEADIN_OUTCOME_KEYS.get(checkin_outcome or "")
    if module_id and outcome_key and has_message(module_key):
        text = get_message(
            "fu_ask_leadin",
            module=get_message(module_key),
            outcome=get_message(outcome_key),
            label=label,
        )
    else:
        text = get_message("fu_ask", label=label)
    return OutboundMessage(
        kind="buttons", text_hi=text, buttons=[_btn(b) for b in OUTCOME_BUTTONS]
    )


def back_to_scene_message(scene: dict[str, object] | None) -> OutboundMessage:
    """One line that returns her to the scene with the board's problem and one thing to ask."""
    board = str((scene or {}).get("board") or "")
    if scene and board and scene.get("mode") == "one_on_one":
        text = get_message("fu_back_one", child=scene.get("child_name"), board=board)
    elif scene and board:
        text = get_message("fu_back_group", board=board)
    else:
        text = get_message("fu_back_setup")
    return OutboundMessage(kind="buttons", text_hi=text, buttons=[_btn(BTN_BACK)])


def why_message() -> OutboundMessage:
    return OutboundMessage(
        kind="buttons",
        text_hi=get_message("fu_why_ask"),
        buttons=[_btn(b) for b in WHY_BUTTONS],
    )


def already_message() -> OutboundMessage:
    return OutboundMessage(kind="text", text_hi=get_message("fu_already"))


@dataclass
class FollowupResult:
    messages: list[OutboundMessage] = field(default_factory=list)
    handled: bool = True
    outcome: str | None = None  # a new outcome to store (the service stores it once)
    reason: str | None = None
    launch_move_id: str | None = None
    handbook: bool = False
    went_worked: bool = False  # the service adds "the next move in your path"
    stage: str = STAGE_NONE


def _other_chunk_reply(s: ClassStruggle, ctx: SessionContext) -> OutboundMessage:
    """A DIFFERENT cited source for this struggle, or the same tip with an honest line."""
    label = struggle_label(s)
    if len(s.chunk_ids) > 1:
        sources, cites = _source_lines(s.chunk_ids[1:], ctx.address_form)
        if cites:
            return OutboundMessage(
                kind="text",
                text_hi=get_message("fu_stuck_other", label=label, sources=sources),
                citations=cites,
            )
    sources, cites = _source_lines(s.chunk_ids[:1], ctx.address_form)
    tip = s.tip_en if get_ui_lang() == "en" else s.tip_hi
    if not cites:
        return OutboundMessage(kind="text", text_hi=get_message("chk_tip_missing", label=label))
    return OutboundMessage(
        kind="text",
        text_hi=get_message("fu_stuck_same", label=label, tip=tip, sources=sources),
        citations=cites,
    )


def stuck_messages(
    s: ClassStruggle, ctx: SessionContext, *, in_scene: bool
) -> list[OutboundMessage]:
    out = [_other_chunk_reply(s, ctx)]
    if s.move_id is not None and not in_scene:
        out.append(
            OutboundMessage(
                kind="buttons",
                text_hi=get_message("fu_stuck_practice", move_title=move_title(s.move_id)),
                buttons=[_btn(BTN_PRACTICE), _btn(BTN_HANDBOOK)],
            )
        )
    elif s.move_id is None:
        out.append(
            OutboundMessage(
                kind="buttons",
                text_hi=get_message("chk_practice_none"),
                buttons=[_btn(BTN_HANDBOOK)],
            )
        )
    return out


def worked_messages(
    s: ClassStruggle | None, next_move_title: str | None, *, offer_next: bool
) -> list[OutboundMessage]:
    """A short acknowledgement and the next move in her path; no praise beyond that."""
    label = struggle_label(s) if s is not None else get_message("fu_unknown_label")
    text = get_message("fu_worked_ack", label=label)
    if next_move_title:
        text = f"{text}\n{get_message('chk_well_next', next_move_title=next_move_title)}"
        if offer_next:
            return [
                OutboundMessage(
                    kind="buttons",
                    text_hi=text,
                    buttons=[Button(id="btn_next_move", title_hi=get_message("btn_next_move"))],
                )
            ]
    return [OutboundMessage(kind="text", text_hi=text)]


def cant_messages(reason: str) -> list[OutboundMessage]:
    """A practical line, never shaming: the level sorter for a multigrade class, else the handbook."""
    if reason == "multigrade":
        buttons = [_btn(BTN_HANDBOOK)]
        if v2_enabled(settings.LEVEL_SORTER_ENABLED):
            buttons = [
                Button(
                    id=level_sorter.BTN_START,
                    title_hi=get_message(level_sorter.BTN_START)[: settings.WEB_BUTTON_TITLE_MAX],
                ),
                *buttons,
            ]
        return [
            OutboundMessage(
                kind="buttons", text_hi=get_message("fu_cant_multigrade"), buttons=buttons
            )
        ]
    key = f"fu_cant_{reason}" if reason in REASONS and has_message(f"fu_cant_{reason}") else None
    return [
        OutboundMessage(
            kind="buttons",
            text_hi=get_message(key or "fu_cant_other"),
            buttons=[_btn(BTN_HANDBOOK)],
        )
    ]


def handle_button(
    ctx: SessionContext,
    button_id: str,
    *,
    struggle_id: str | None,
    answered: bool,
    in_scene: bool,
    lib: StruggleLibrary | None = None,
) -> FollowupResult:
    """One follow-up tap. `answered` says an outcome is already stored for the open follow-up.

    A second tap of an outcome button (or any outcome button after it was answered) stores nothing
    and says so; "why" and the practice / handbook buttons work after "could not try" / "still stuck".
    """
    lib = lib or load_library()
    struggle = lib.get(struggle_id) if struggle_id else None
    if button_id in OUTCOME_BUTTONS:
        if answered or struggle_id is None:
            return FollowupResult([already_message()])
        outcome = OUTCOME_BUTTONS[button_id]
        if outcome == OUTCOME_WORKED:
            ctx.followup_stage = STAGE_NONE
            return FollowupResult(outcome=outcome, went_worked=True)
        if outcome == OUTCOME_CANT:
            ctx.followup_stage = STAGE_WHY
            return FollowupResult([why_message()], outcome=outcome, stage=STAGE_WHY)
        ctx.followup_stage = STAGE_NONE
        if struggle is None:
            return FollowupResult(
                [OutboundMessage(kind="text", text_hi=get_message("fu_stuck_missing"))],
                outcome=outcome,
            )
        return FollowupResult(stuck_messages(struggle, ctx, in_scene=in_scene), outcome=outcome)
    if button_id in WHY_BUTTONS:
        if ctx.followup_stage != STAGE_WHY:
            return FollowupResult([already_message()])
        reason = WHY_BUTTONS[button_id]
        ctx.followup_stage = STAGE_NONE
        return FollowupResult(cant_messages(reason), reason=reason)
    if button_id == BTN_PRACTICE:
        move_id = struggle.move_id if struggle is not None else None
        if move_id is None or in_scene:
            return FollowupResult([already_message()])
        return FollowupResult(launch_move_id=move_id)
    if button_id == BTN_HANDBOOK:
        return FollowupResult(handbook=True, handled=False)
    return FollowupResult(handled=False)


@dataclass(frozen=True)
class TomorrowFocus:
    """One cited step from her last struggle, for an opt-in weekly "tomorrow's focus" note."""

    struggle_id: str
    text: str
    citations: tuple[Citation, ...]


def tomorrow_focus(
    last_struggle_id: str | None,
    *,
    opted_in: bool,
    address_form: str = "f",
    lib: StruggleLibrary | None = None,
) -> TomorrowFocus | None:
    """A pure function: the one step (the struggle's stored tip and its citations) or None.

    None when she has not opted in, has no struggle, the struggle is unknown, or no stored chunk
    backs the tip (a focus is never sent without its citation). Nothing is sent from here.
    """
    if not opted_in or not last_struggle_id:
        return None
    s = (lib or load_library()).get(last_struggle_id)
    if s is None:
        return None
    sources, cites = _source_lines(s.chunk_ids, address_form)
    if not cites:
        return None
    tip = s.tip_en if get_ui_lang() == "en" else s.tip_hi
    text = get_message("fu_tomorrow_focus", label=struggle_label(s), tip=tip, sources=sources)
    return TomorrowFocus(s.id, text, tuple(cites))


__all__ = [
    "ALL_BUTTONS",
    "BTN_BACK",
    "BTN_CANT",
    "BTN_HANDBOOK",
    "BTN_PRACTICE",
    "BTN_STUCK",
    "BTN_WORKED",
    "FollowupResult",
    "OUTCOMES",
    "REASONS",
    "TomorrowFocus",
    "ask_message",
    "back_to_scene_message",
    "cant_messages",
    "due_date_for",
    "enabled",
    "handle_button",
    "is_due",
    "ist_date",
    "next_school_day",
    "stuck_messages",
    "tomorrow_focus",
    "utcnow",
    "worked_messages",
]
