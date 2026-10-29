"""The "After class: how did it go?" check-in: four taps, closed lists, no free text.

Module -> went well / some / most struggled -> (if struggled) which difficulty -> one tip.
Everything she can pick is derived from content that already exists: the modules from the
`move_id`s in `content/class_struggles.yaml` (struggles with no move share one "other topics"
module per domain), the difficulties from that file, the tip from the struggle's own stored
paraphrase with the citations of its handbook chunks. Nothing is generated, so the whole flow works
with no LLM. State lives on `SessionContext` (`checkin_*`); this module mutates it and returns
messages plus, when a check-in is complete, the record the service stores (ids only).

Buttons are catalog keys, so the English UI localises them (`btn_chk_mod_<module>`,
`btn_chk_str_<struggle>`, ...). At most `settings.CHECKIN_MAX_BUTTONS` (the web cap) per screen; a "more" button
pages through a longer list. The WhatsApp channel re-renders a screen with more than 3 options as
an interactive list and shortens titles to 20 characters (`channels/whatsapp/buttons.py`).
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field

from backend.app.class_profile.library import (
    ClassStruggle,
    StruggleLibrary,
    citations,
    load_library,
)
from backend.app.config import settings
from backend.app.core.intents import Intent
from backend.app.core.messages import get_message, get_ui_lang, has_message
from backend.app.core.types import Button, Citation, OutboundMessage
from backend.app.llm.roles.guide_answerer import format_guide_citation
from backend.app.sessions.state_machine import (
    SessionContext,
    SessionStateEnum,
)
from backend.app.sessions.titles import move_title
from backend.app.sessions.training_rating import is_rating_escape

STAGE_NONE = ""
STAGE_MODULE = "module"
STAGE_OUTCOME = "outcome"
STAGE_STRUGGLE = "struggle"
STAGE_RESULT = "result"

OUTCOME_WELL = "well"
OUTCOME_SOME = "some"
OUTCOME_MOST = "most"

BTN_START = "btn_chk_start"
BTN_MORE = "btn_chk_more"
BTN_PRACTICE = "btn_chk_practice"
BTN_HANDBOOK = "btn_chk_handbook"
BTN_RESUME = "btn_chk_resume"
MODULE_PREFIX = "btn_chk_mod_"
STRUGGLE_PREFIX = "btn_chk_str_"
OUTCOME_BUTTONS = {
    "btn_chk_well": OUTCOME_WELL,
    "btn_chk_some": OUTCOME_SOME,
    "btn_chk_most": OUTCOME_MOST,
}

_OTHER_PREFIX = "OTHER_"
_TRAILING = " .!?।,"
_SCENE_SETUP = SessionStateEnum.REHEARSE_INTRO  # picking the child: no check-in here
_SCENE = SessionStateEnum.REHEARSE  # a running scene: paused by the check-in, not touched


@dataclass(frozen=True)
class CheckinModule:
    id: str
    struggle_ids: tuple[str, ...]


@dataclass(frozen=True)
class CheckinRecord:
    """What the service stores: ids from the closed lists only."""

    module_id: str
    outcome: str
    struggle_ids: tuple[str, ...]


@dataclass
class CheckinResult:
    messages: list[OutboundMessage] = field(default_factory=list)
    handled: bool = True
    record: CheckinRecord | None = None
    went_well: bool = False  # the service adds the "next move in your path" line
    launch_move_id: str | None = None  # open the practice scene for this move
    handbook: bool = False  # carry on as the handbook-question button
    resume_scene: bool = False  # back to the paused scene (the service says where she was)


def modules(lib: StruggleLibrary | None = None) -> list[CheckinModule]:
    """Modules derived from the library: each move, then one "other topics" module per domain."""
    lib = lib or load_library()
    groups: dict[str, list[str]] = {}
    for s in lib.struggles:
        groups.setdefault(s.move_id or f"{_OTHER_PREFIX}{s.domain}", []).append(s.id)
    moves = [
        CheckinModule(k, tuple(v)) for k, v in groups.items() if not k.startswith(_OTHER_PREFIX)
    ]
    others = [CheckinModule(k, tuple(v)) for k, v in groups.items() if k.startswith(_OTHER_PREFIX)]
    return moves + others


def _module(module_id: str, lib: StruggleLibrary) -> CheckinModule | None:
    return next((m for m in modules(lib) if m.id == module_id), None)


def _btn(button_id: str, fallback: str = "") -> Button:
    title = get_message(button_id) if has_message(button_id) else fallback
    return Button(id=button_id, title_hi=title[: settings.WEB_BUTTON_TITLE_MAX])


def module_label(module_id: str) -> str:
    key = f"{MODULE_PREFIX}{module_id}"
    if has_message(key):
        return get_message(key)
    return move_title(module_id)


def struggle_label(s: ClassStruggle) -> str:
    key = f"{STRUGGLE_PREFIX}{s.id}"
    if has_message(key):
        return get_message(key)
    return s.label_en if get_ui_lang() == "en" else s.label_hi


def _paged(buttons: list[Button], page: int) -> list[Button]:
    """At most CHECKIN_MAX_BUTTONS: a longer list is cut into pages, each ending in "more"."""
    limit = settings.CHECKIN_MAX_BUTTONS
    if len(buttons) <= limit:
        return buttons
    per_page = limit - 1
    pages = -(-len(buttons) // per_page)
    start = (page % pages) * per_page
    return [*buttons[start : start + per_page], _btn(BTN_MORE)]


def _module_screen(ctx: SessionContext, lib: StruggleLibrary, *, key: str) -> OutboundMessage:
    ctx.checkin_stage = STAGE_MODULE
    buttons = [_btn(f"{MODULE_PREFIX}{m.id}", move_title(m.id)) for m in modules(lib)]
    return OutboundMessage(
        kind="buttons", text_hi=get_message(key), buttons=_paged(buttons, ctx.checkin_page)
    )


def _outcome_screen(ctx: SessionContext) -> OutboundMessage:
    ctx.checkin_stage = STAGE_OUTCOME
    return OutboundMessage(
        kind="buttons",
        text_hi=get_message("chk_outcome_ask", module=module_label(ctx.checkin_module)),
        buttons=[_btn(b) for b in OUTCOME_BUTTONS],
    )


def _struggle_screen(ctx: SessionContext, lib: StruggleLibrary) -> OutboundMessage:
    ctx.checkin_stage = STAGE_STRUGGLE
    module = _module(ctx.checkin_module, lib)
    items = [lib.get(sid) for sid in (module.struggle_ids if module else ())]
    buttons = [_btn(f"{STRUGGLE_PREFIX}{s.id}", s.chip_hi) for s in items if s is not None]
    return OutboundMessage(
        kind="buttons",
        text_hi=get_message("chk_struggle_ask", module=module_label(ctx.checkin_module)),
        buttons=_paged(buttons, ctx.checkin_page),
    )


def _screen(ctx: SessionContext, lib: StruggleLibrary, *, note: bool = False) -> OutboundMessage:
    """The screen for the current stage (shown again when she types instead of tapping)."""
    if ctx.checkin_stage == STAGE_OUTCOME:
        msg = _outcome_screen(ctx)
    elif ctx.checkin_stage == STAGE_STRUGGLE:
        msg = _struggle_screen(ctx, lib)
    else:
        msg = _module_screen(ctx, lib, key="chk_module_ask")
    if note:
        msg = msg.model_copy(update={"text_hi": f"{get_message('chk_pick_button')}\n{msg.text_hi}"})
    return msg


def _source_lines(chunk_ids: list[str], address_form: str) -> tuple[str, list[Citation]]:
    """One citation line and chip per stored chunk of the struggle (unknown ids are skipped)."""
    lines: list[str] = []
    cites: list[Citation] = []
    for c in citations(chunk_ids):
        line = format_guide_citation(c.source_short_hi, c.page, address_form=address_form)
        lines.append(line)
        cites.append(
            Citation(
                chunk_id=c.chunk_id, source_short_hi=c.source_short_hi, page=c.page, line_hi=line
            )
        )
    return "\n".join(lines), cites


def result_messages(ctx: SessionContext, s: ClassStruggle) -> list[OutboundMessage]:
    """The tip with its citations, then the practice offer (honest when there is no move yet)."""
    label = struggle_label(s)
    sources, cites = _source_lines(s.chunk_ids, ctx.address_form)
    tip = s.tip_en if get_ui_lang() == "en" else s.tip_hi
    if cites:
        tip_msg = OutboundMessage(
            kind="text",
            text_hi=get_message("chk_tip", label=label, tip=tip, sources=sources),
            citations=cites,
        )
    else:
        tip_msg = OutboundMessage(kind="text", text_hi=get_message("chk_tip_missing", label=label))
    if ctx.current_state == _SCENE:  # the scene is paused: no second practice, offer the way back
        key = "chk_in_scene_practice" if s.move_id is not None else "chk_scene_waiting"
        offer = OutboundMessage(
            kind="buttons",
            text_hi=get_message(key, move_title=move_title(s.move_id) if s.move_id else ""),
            buttons=[_btn(BTN_RESUME), _btn(BTN_HANDBOOK)],
        )
    elif s.move_id is not None:
        offer = OutboundMessage(
            kind="buttons",
            text_hi=get_message("chk_practice_yes", move_title=move_title(s.move_id)),
            buttons=[_btn(BTN_PRACTICE), _btn(BTN_HANDBOOK)],
        )
    else:
        offer = OutboundMessage(
            kind="buttons",
            text_hi=get_message("chk_practice_none"),
            buttons=[_btn(BTN_HANDBOOK)],
        )
    return [tip_msg, offer]


def well_messages(
    ctx: SessionContext, next_move_title: str | None, *, offer_next: bool
) -> list[OutboundMessage]:
    """A short acknowledgement and the next move in her path (no praise beyond that)."""
    text = get_message("chk_well_ack", module=module_label(ctx.checkin_module))
    if ctx.current_state == _SCENE:  # the paused scene is what comes next, not another move
        return [
            OutboundMessage(
                kind="buttons",
                text_hi=f"{text}\n{get_message('chk_scene_waiting')}",
                buttons=[_btn(BTN_RESUME)],
            )
        ]
    if next_move_title:
        text = f"{text}\n{get_message('chk_well_next', next_move_title=next_move_title)}"
    if next_move_title and offer_next:
        return [
            OutboundMessage(
                kind="buttons",
                text_hi=text,
                buttons=[Button(id="btn_next_move", title_hi=get_message("btn_next_move"))],
            )
        ]
    return [OutboundMessage(kind="text", text_hi=text)]


def is_checkin_command(text: str) -> bool:
    cleaned = unicodedata.normalize("NFC", text or "").strip(_TRAILING).strip().lower()
    if not cleaned:
        return False
    for lang in ("hi", "en"):
        raw = get_message("chk_command_words", lang=lang)
        words = {unicodedata.normalize("NFC", w).strip().lower() for w in raw.split(",")}
        if cleaned in words:
            return True
    return False


def _reset(ctx: SessionContext) -> None:
    ctx.checkin_stage = STAGE_NONE
    ctx.checkin_module = ""
    ctx.checkin_outcome = ""
    ctx.checkin_struggle = ""
    ctx.checkin_page = 0


def start(ctx: SessionContext, lib: StruggleLibrary | None = None) -> CheckinResult:
    lib = lib or load_library()
    _reset(ctx)
    return CheckinResult([_module_screen(ctx, lib, key="chk_module_ask")])


def handle(
    ctx: SessionContext,
    text: str,
    button_id: str | None,
    intent: Intent | None,
    lib: StruggleLibrary | None = None,
) -> CheckinResult:
    """One inbound message. `handled=False` means "not mine, carry on with normal routing"."""
    lib = lib or load_library()
    text = (text or "").strip()
    in_setup = ctx.current_state == _SCENE_SETUP
    in_scene = ctx.current_state == _SCENE

    if button_id == BTN_START:  # the chip also works inside a running scene (it is paused)
        return CheckinResult(handled=False) if in_setup else start(ctx, lib)
    if ctx.checkin_stage == STAGE_NONE and not button_id and is_checkin_command(text):
        # typed words inside a scene are her line to the child, never a command
        return CheckinResult(handled=False) if in_setup or in_scene else start(ctx, lib)

    if button_id == BTN_RESUME and in_scene:
        _reset(ctx)
        return CheckinResult(resume_scene=True)

    is_checkin_button = bool(button_id) and str(button_id).startswith("btn_chk_")
    if ctx.checkin_stage == STAGE_NONE:
        if is_checkin_button:  # a button from an earlier, finished check-in
            return CheckinResult([OutboundMessage(kind="text", text_hi=get_message("chk_already"))])
        return CheckinResult(handled=False)

    if ctx.checkin_stage == STAGE_RESULT:
        if button_id == BTN_PRACTICE:
            chosen = lib.get(ctx.checkin_struggle)
            move_id = chosen.move_id if chosen is not None else None
            _reset(ctx)
            if move_id is None:
                return CheckinResult(handled=False)
            return CheckinResult(launch_move_id=move_id)
        if button_id == BTN_HANDBOOK:
            _reset(ctx)
            return CheckinResult(handbook=True, handled=False)
        if is_checkin_button:  # the same tap twice, or an old button: nothing is stored again
            return CheckinResult([OutboundMessage(kind="text", text_hi=get_message("chk_already"))])
        _reset(ctx)
        return CheckinResult(handled=False)

    if not button_id:
        if not text or in_scene or is_rating_escape(intent, text):
            # a command (menu, next, ask ...) ends the check-in and runs normally; inside a paused
            # scene her typing is the next line to the child, so the check-in is dropped (unsaved)
            _reset(ctx)
            return CheckinResult(handled=False)
        return CheckinResult([_screen(ctx, lib, note=True)])

    if button_id == BTN_MORE:
        ctx.checkin_page += 1
        return CheckinResult([_screen(ctx, lib)])

    if ctx.checkin_stage == STAGE_MODULE and button_id.startswith(MODULE_PREFIX):
        module_id = button_id[len(MODULE_PREFIX) :]
        if _module(module_id, lib) is not None:
            ctx.checkin_module = module_id
            ctx.checkin_page = 0
            return CheckinResult([_outcome_screen(ctx)])

    elif ctx.checkin_stage == STAGE_OUTCOME and button_id in OUTCOME_BUTTONS:
        outcome = OUTCOME_BUTTONS[button_id]
        if outcome == OUTCOME_WELL:
            record = CheckinRecord(ctx.checkin_module, OUTCOME_WELL, ())
            messages = CheckinResult(went_well=True, record=record)
            return messages  # the service adds the next-move line, then resets via `finish`
        ctx.checkin_outcome = outcome
        ctx.checkin_page = 0
        return CheckinResult([_struggle_screen(ctx, lib)])

    elif ctx.checkin_stage == STAGE_STRUGGLE and button_id.startswith(STRUGGLE_PREFIX):
        module = _module(ctx.checkin_module, lib)
        struggle_id = button_id[len(STRUGGLE_PREFIX) :]
        struggle = lib.get(struggle_id)
        if module is not None and struggle is not None and struggle_id in module.struggle_ids:
            record = CheckinRecord(ctx.checkin_module, ctx.checkin_outcome, (struggle_id,))
            ctx.checkin_struggle = struggle_id
            ctx.checkin_stage = STAGE_RESULT
            return CheckinResult(result_messages(ctx, struggle), record=record)

    return CheckinResult([_screen(ctx, lib, note=True)])  # not a button of this screen


def finish(ctx: SessionContext) -> None:
    """The check-in is complete and has no follow-up buttons (went well): clear the state."""
    _reset(ctx)


__all__ = [
    "BTN_HANDBOOK",
    "BTN_MORE",
    "BTN_PRACTICE",
    "BTN_RESUME",
    "BTN_START",
    "CheckinModule",
    "CheckinRecord",
    "CheckinResult",
    "OUTCOME_BUTTONS",
    "finish",
    "handle",
    "is_checkin_command",
    "modules",
    "module_label",
    "result_messages",
    "start",
    "struggle_label",
    "well_messages",
]
