"""The "My class" conversation: ask, understand, confirm, save (chat channels).

State lives on `SessionContext` (`class_stage`, `class_pending`, `class_struggles`); this module
mutates it and returns the messages. `resolve_struggles` is the only place text becomes ids: the
`class_struggle_classifier` role first, then the deterministic keyword matcher. Whatever comes out
is filtered through the closed library, so nothing outside `content/class_struggles.yaml` can be
stored, whatever the model or the teacher says.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Literal

from backend.app.class_profile.library import (
    ClassStruggle,
    StruggleLibrary,
    citations,
    load_library,
)
from backend.app.class_profile.matcher import clip_input, match_struggles
from backend.app.config import settings
from backend.app.core.intents import Intent
from backend.app.core.messages import get_message, get_ui_lang
from backend.app.core.types import Button, Citation, OutboundMessage
from backend.app.llm.roles.class_struggle_classifier import classify_class_struggles
from backend.app.llm.roles.guide_answerer import format_guide_citation
from backend.app.sessions.state_machine import SessionContext
from backend.app.sessions.titles import move_title
from backend.app.sessions.training_rating import is_rating_escape

STAGE_NONE = ""
STAGE_ASKING = "asking"
STAGE_CONFIRM = "confirm"

BTN_START = "btn_cls_start"
BTN_SKIP = "btn_cls_skip"

_COMMAND_WORDS_KEY = "class_command_words"
_TRAILING = " .!?।,"
_DEVANAGARI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")
_NUMBER_REPLY = re.compile(r"^(?:\d+|and|aur|और|[\s,.&])+$")


@dataclass
class Resolution:
    ids: list[str]
    source: Literal["llm", "keywords", "none"]


@dataclass
class FlowResult:
    messages: list[OutboundMessage] = field(default_factory=list)
    handled: bool = True
    saved: bool = False  # the stored choice changed: the caller reorders the path


def _lang() -> str:
    return get_ui_lang()


def _label(s: ClassStruggle) -> str:
    return s.label_en if _lang() == "en" else s.label_hi


def _chip(s: ClassStruggle) -> str:
    return (s.chip_en if _lang() == "en" else s.chip_hi) or _label(s)


def _tip(s: ClassStruggle) -> str:
    return s.tip_en if _lang() == "en" else s.tip_hi


def chip_list_text(lib: StruggleLibrary | None = None) -> str:
    """Numbered chips, then "something else" (the last number), for chat channels."""
    lib = lib or load_library()
    lines = [f"{i}. {_chip(s)}" for i, s in enumerate(lib.chips(), start=1)]
    lines.append(f"{len(lines) + 1}. {get_message('class_other_item')}")
    return "\n".join(lines)


def source_line(chunk_ids: list[str], address_form: str) -> tuple[str, list[Citation]]:
    """The first cited chunk as the standard source line plus its Citation."""
    found = citations(chunk_ids)
    if not found:
        return "", []
    first = found[0]
    line = format_guide_citation(first.source_short_hi, first.page, address_form=address_form)
    cite = Citation(
        chunk_id=first.chunk_id,
        source_short_hi=first.source_short_hi,
        page=first.page,
        line_hi=line,
    )
    return line, [cite]


def practice_line(s: ClassStruggle) -> str:
    if s.move_id is None:
        return get_message("class_practice_none")
    title = move_title(s.move_id)
    return get_message("class_practice_yes", move_title=title)


def items_text(
    ids: list[str], address_form: str, lib: StruggleLibrary, *, full: bool
) -> tuple[str, list[Citation]]:
    lines: list[str] = []
    cites: list[Citation] = []
    for n, sid in enumerate(ids, start=1):
        s = lib.get(sid)
        if s is None:
            continue
        if not full:
            lines.append(get_message("class_item_short", n=n, label=_label(s)))
            continue
        src, cs = source_line(s.chunk_ids, address_form)
        cites.extend(cs)
        lines.append(
            get_message(
                "class_item",
                n=n,
                label=_label(s),
                tip=_tip(s),
                practice=practice_line(s),
                source=src,
            )
        )
    return "\n".join(lines), cites


def clean_ids(ids: list[str], lib: StruggleLibrary | None = None) -> list[str]:
    """Only library ids, no repeats, in order, at most STRUGGLE_MAX_CHOSEN."""
    lib = lib or load_library()
    known = set(lib.ids())
    out: list[str] = []
    for sid in ids:
        if sid in known and sid not in out:
            out.append(sid)
    return out[: settings.STRUGGLE_MAX_CHOSEN]


async def resolve_struggles(text: str, lib: StruggleLibrary | None = None) -> Resolution:
    """Her words -> library ids: classifier role, else keyword matcher, else nothing."""
    lib = lib or load_library()
    clean = clip_input(unicodedata.normalize("NFC", text or "")).strip()
    if not clean:
        return Resolution([], "none")
    candidates = {s.id: f"{s.label_en} ({s.label_hi})" for s in lib.struggles}
    llm_ids = await classify_class_struggles(clean, candidates)
    ids = clean_ids(llm_ids or [], lib)
    if ids:
        return Resolution(ids, "llm")
    ids = clean_ids([m.struggle_id for m in match_struggles(clean, lib)], lib)
    if ids:
        return Resolution(ids, "keywords")
    return Resolution([], "none")


def parse_number_choice(text: str, lib: StruggleLibrary | None = None) -> list[str] | None:
    """A number reply ("2", "1, 3", "१ और ३") -> ids by chip number.

    None if the text is not a number reply; [] if it is only the "something else" number or
    out of range.
    """
    lib = lib or load_library()
    cleaned = unicodedata.normalize("NFC", text or "").translate(_DEVANAGARI_DIGITS).lower()
    cleaned = cleaned.strip(_TRAILING)
    if not cleaned or not re.search(r"\d", cleaned) or not _NUMBER_REPLY.match(cleaned):
        return None
    chips = lib.chips()
    ids: list[str] = []
    for num in re.findall(r"\d+", cleaned):
        n = int(num)
        if 1 <= n <= len(chips):
            ids.append(chips[n - 1].id)
    return clean_ids(ids, lib)


def is_class_command(text: str) -> bool:
    cleaned = unicodedata.normalize("NFC", text or "").strip(_TRAILING).strip().lower()
    if not cleaned:
        return False
    for lang in ("hi", "en"):
        raw = get_message(_COMMAND_WORDS_KEY, lang=lang)
        words = {unicodedata.normalize("NFC", w).strip().lower() for w in raw.split(",")}
        if cleaned in words:
            return True
    return False


HELPED_YES = "yes"
HELPED_SOME = "some"
HELPED_NO = "no"
_HELPED_BUTTONS = {
    "btn_helped_yes": HELPED_YES,
    "btn_helped_some": HELPED_SOME,
    "btn_helped_no": HELPED_NO,
}
_HELPED_WORDS: tuple[tuple[str, frozenset[str]], ...] = (
    (HELPED_SOME, frozenset({"थोड़ी", "थोड़ा", "कुछ", "some", "little", "thodi", "thoda", "partly"})),
    (HELPED_NO, frozenset({"नहीं", "नही", "ना", "no", "nahi", "not"})),
    (HELPED_YES, frozenset({"हाँ", "हां", "मदद", "yes", "ha", "haan", "helped", "हुआ"})),
)


def parse_helped(text: str, button_id: str | None) -> str | None:
    """ "Did it help your class?" -> yes / some / no, from a button or a typed or spoken word."""
    if button_id in _HELPED_BUTTONS:
        return _HELPED_BUTTONS[button_id]
    cleaned = unicodedata.normalize("NFC", text or "").lower()
    words = {w for w in re.split(r"[\s,.!?।]+", cleaned) if w}
    for answer, vocabulary in _HELPED_WORDS:
        if words & vocabulary:
            return answer
    return None


def helped_message() -> OutboundMessage:
    return OutboundMessage(
        kind="buttons",
        text_hi=get_message("class_helped_ask"),
        buttons=[
            Button(id="btn_helped_yes", title_hi=get_message("btn_helped_yes")),
            Button(id="btn_helped_some", title_hi=get_message("btn_helped_some")),
            Button(id="btn_helped_no", title_hi=get_message("btn_helped_no")),
        ],
    )


def ask_message(lib: StruggleLibrary | None = None) -> OutboundMessage:
    return OutboundMessage(
        kind="buttons",
        text_hi=get_message("class_ask", list=chip_list_text(lib)),
        buttons=[Button(id=BTN_SKIP, title_hi=get_message("btn_cls_skip"))],
    )


def invite_message() -> OutboundMessage:
    """The optional prompt shown once after onboarding."""
    return OutboundMessage(
        kind="buttons",
        text_hi=get_message("class_ask_invite"),
        buttons=[
            Button(id=BTN_START, title_hi=get_message("btn_cls_start")),
            Button(id=BTN_SKIP, title_hi=get_message("btn_cls_skip")),
        ],
    )


def start(ctx: SessionContext) -> FlowResult:
    ctx.class_stage = STAGE_ASKING
    ctx.class_pending = []
    return FlowResult([ask_message()])


def _no_match(address_form: str, lib: StruggleLibrary) -> OutboundMessage:
    src, cites = source_line(lib.other.chunk_ids, address_form)
    tip = lib.other.tip_en if _lang() == "en" else lib.other.tip_hi
    return OutboundMessage(
        kind="buttons",
        text_hi=get_message("class_no_match", tip=tip, source=src),
        citations=cites,
        buttons=[Button(id=BTN_SKIP, title_hi=get_message("btn_cls_skip"))],
    )


def _confirm(ctx: SessionContext, ids: list[str], lib: StruggleLibrary) -> OutboundMessage:
    ctx.class_pending = ids
    ctx.class_stage = STAGE_CONFIRM
    items, _ = items_text(ids, ctx.address_form, lib, full=False)
    return OutboundMessage(
        kind="buttons",
        text_hi=get_message("class_confirm", items=items),
        buttons=[
            Button(id="btn_yes", title_hi=get_message("btn_yes")),
            Button(id="btn_no", title_hi=get_message("btn_no")),
        ],
    )


def save(ctx: SessionContext, ids: list[str], lib: StruggleLibrary) -> FlowResult:
    ids = clean_ids(ids, lib)
    ctx.class_struggles = ids
    ctx.class_stage = STAGE_NONE
    ctx.class_pending = []
    items, cites = items_text(ids, ctx.address_form, lib, full=True)
    msg = OutboundMessage(
        kind="text", text_hi=get_message("class_saved", items=items), citations=cites
    )
    return FlowResult([msg], saved=True)


async def handle(
    ctx: SessionContext,
    text: str,
    button_id: str | None,
    intent: Intent | None,
    lib: StruggleLibrary | None = None,
) -> FlowResult:
    """One inbound message. `handled=False` means "not mine, carry on with normal routing"."""
    lib = lib or load_library()
    text = (text or "").strip()

    if button_id == BTN_SKIP:
        ctx.class_stage = STAGE_NONE
        ctx.class_pending = []
        return FlowResult([OutboundMessage(kind="text", text_hi=get_message("class_skipped"))])
    if button_id == BTN_START or (ctx.class_stage == STAGE_NONE and is_class_command(text)):
        return start(ctx)
    if ctx.class_stage == STAGE_NONE:
        return FlowResult(handled=False)

    if ctx.class_stage == STAGE_CONFIRM:
        if button_id == "btn_yes" or intent == Intent.CONFIRM_YES:
            return save(ctx, ctx.class_pending, lib)
        if button_id == "btn_no" or intent == Intent.CONFIRM_NO:
            return start(ctx)

    numbers = parse_number_choice(text, lib)
    if not text or (numbers is None and is_rating_escape(intent, text)):
        # A command (menu, next, ask ...) ends the prompt and is processed normally.
        ctx.class_stage = STAGE_NONE
        ctx.class_pending = []
        return FlowResult(handled=False)

    ids = numbers if numbers is not None else (await resolve_struggles(text, lib)).ids
    if not ids:
        ctx.class_stage = STAGE_ASKING
        return FlowResult([_no_match(ctx.address_form, lib)])
    return FlowResult([_confirm(ctx, ids, lib)])
