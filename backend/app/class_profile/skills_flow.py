"""The "What do you want to get better at?" conversation: ask, understand, confirm, save.

Runs right after her class choice is saved (or from the My class page). State lives on
`SessionContext` (`skill_stage`, `skill_pending`, `teaching_skills`). `resolve_skills` is the only
place text becomes ids: the `teaching_skill_classifier` role (closed list, guarded), and when it is
unavailable or finds nothing, the chips again (a numbered list she answers with a number or a tap).
Whatever comes out is filtered through the closed list, so nothing outside
`content/teaching_skills.yaml` can be stored, whatever the model or the teacher says.
"""

from __future__ import annotations

import re
import unicodedata

from backend.app.class_profile import flow as class_flow
from backend.app.class_profile.matcher import clip_input
from backend.app.class_profile.skills import (
    OTHER_ID,
    SkillLibrary,
    TeachingSkill,
    clean_skill_ids,
    load_skills,
    resolve_candidates,
)
from backend.app.config import settings
from backend.app.core.intents import Intent
from backend.app.core.messages import get_message, get_ui_lang
from backend.app.core.types import Button, Citation, OutboundMessage
from backend.app.llm.roles.teaching_skill_classifier import classify_teaching_skills
from backend.app.sessions.state_machine import SessionContext
from backend.app.sessions.training_rating import is_rating_escape

STAGE_NONE = ""
STAGE_ASKING = "asking"
STAGE_CONFIRM = "confirm"

BTN_SKIP = "btn_skill_skip"

_TRAILING = " .!?।,"
_DEVANAGARI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")
_NUMBER_REPLY = re.compile(r"^(?:\d+|and|aur|और|[\s,.&])+$")


def _label(s: TeachingSkill) -> str:
    return s.label_en if get_ui_lang() == "en" else s.label_hi


def chip_list_text(lib: SkillLibrary | None = None) -> str:
    """Numbered skills, "something else" last, for chat channels."""
    lib = lib or load_skills()
    return "\n".join(f"{i}. {_label(s)}" for i, s in enumerate(lib.skills, start=1))


def parse_number_choice(text: str, lib: SkillLibrary | None = None) -> list[str] | None:
    """A number reply ("2", "1, 3", "१ और ३") -> ids by list number; None if not a number reply."""
    lib = lib or load_skills()
    cleaned = unicodedata.normalize("NFC", text or "").translate(_DEVANAGARI_DIGITS).lower()
    cleaned = cleaned.strip(_TRAILING)
    if not cleaned or not re.search(r"\d", cleaned) or not _NUMBER_REPLY.match(cleaned):
        return None
    ids: list[str] = []
    for num in re.findall(r"\d+", cleaned):
        n = int(num)
        if 1 <= n <= len(lib.skills):
            ids.append(lib.skills[n - 1].id)
    return clean_skill_ids(ids, lib)


async def resolve_skills(text: str, lib: SkillLibrary | None = None) -> list[str]:
    """Her words -> library ids: the classifier (closed list), else nothing (the caller shows chips)."""
    lib = lib or load_skills()
    clean = clip_input(unicodedata.normalize("NFC", text or "")).strip()
    if not clean:
        return []
    ids = await classify_teaching_skills(clean, resolve_candidates(lib))
    return clean_skill_ids(ids or [], lib)


def items_text(
    ids: list[str], address_form: str, lib: SkillLibrary, *, full: bool
) -> tuple[str, list[Citation]]:
    lines: list[str] = []
    cites: list[Citation] = []
    for n, sid in enumerate(ids, start=1):
        s = lib.get(sid)
        if s is None:
            continue
        if not full:
            lines.append(get_message("class_item_short", n=n, label=_label(s)))
        elif s.chunk_id:
            src, cs = class_flow.source_line([s.chunk_id], address_form)
            cites.extend(cs)
            lines.append(get_message("skill_item", n=n, label=_label(s), source=src))
        else:
            lines.append(get_message("skill_item_other", n=n, label=_label(s)))
    return "\n".join(lines), cites


def ask_message(lib: SkillLibrary | None = None) -> OutboundMessage:
    return OutboundMessage(
        kind="buttons",
        text_hi=get_message(
            "skill_ask", list=chip_list_text(lib), max=settings.TEACHING_SKILLS_MAX
        ),
        buttons=[Button(id=BTN_SKIP, title_hi=get_message("btn_skill_skip"))],
    )


def start(ctx: SessionContext) -> class_flow.FlowResult:
    ctx.skill_stage = STAGE_ASKING
    ctx.skill_pending = []
    return class_flow.FlowResult([ask_message()])


def save(ctx: SessionContext, ids: list[str], lib: SkillLibrary) -> class_flow.FlowResult:
    ids = clean_skill_ids(ids, lib)
    ctx.teaching_skills = ids
    ctx.skill_stage = STAGE_NONE
    ctx.skill_pending = []
    items, cites = items_text(ids, ctx.address_form, lib, full=True)
    msg = OutboundMessage(
        kind="text", text_hi=get_message("skill_saved", items=items), citations=cites
    )
    return class_flow.FlowResult([msg], saved=True)


def _confirm(ctx: SessionContext, ids: list[str], lib: SkillLibrary) -> OutboundMessage:
    ctx.skill_pending = ids
    ctx.skill_stage = STAGE_CONFIRM
    items, _ = items_text(ids, ctx.address_form, lib, full=False)
    return OutboundMessage(
        kind="buttons",
        text_hi=get_message("skill_confirm", items=items),
        buttons=[
            Button(id="btn_yes", title_hi=get_message("btn_yes")),
            Button(id="btn_no", title_hi=get_message("btn_no")),
        ],
    )


def _chips_again(lib: SkillLibrary) -> OutboundMessage:
    return OutboundMessage(
        kind="buttons",
        text_hi=get_message("skill_no_match", list=chip_list_text(lib)),
        buttons=[Button(id=BTN_SKIP, title_hi=get_message("btn_skill_skip"))],
    )


async def handle(
    ctx: SessionContext,
    text: str,
    button_id: str | None,
    intent: Intent | None,
    lib: SkillLibrary | None = None,
) -> class_flow.FlowResult:
    """One inbound message. `handled=False` means "not mine, carry on with normal routing"."""
    lib = lib or load_skills()
    text = (text or "").strip()
    if ctx.skill_stage == STAGE_NONE:
        return class_flow.FlowResult(handled=False)

    if button_id == BTN_SKIP:
        ctx.skill_stage = STAGE_NONE
        ctx.skill_pending = []
        return class_flow.FlowResult(
            [OutboundMessage(kind="text", text_hi=get_message("skill_skipped"))]
        )

    if ctx.skill_stage == STAGE_CONFIRM:
        if button_id == "btn_yes" or intent == Intent.CONFIRM_YES:
            return save(ctx, ctx.skill_pending, lib)
        if button_id == "btn_no" or intent == Intent.CONFIRM_NO:
            return start(ctx)

    numbers = parse_number_choice(text, lib)
    if not text or (numbers is None and is_rating_escape(intent, text)):
        # A command (menu, next, ask ...) ends the prompt and is processed normally.
        ctx.skill_stage = STAGE_NONE
        ctx.skill_pending = []
        return class_flow.FlowResult(handled=False)

    ids = numbers if numbers is not None else await resolve_skills(text, lib)
    if not ids:
        ctx.skill_stage = STAGE_ASKING
        return class_flow.FlowResult([_chips_again(lib)])
    return class_flow.FlowResult([_confirm(ctx, ids, lib)])


__all__ = [
    "BTN_SKIP",
    "OTHER_ID",
    "STAGE_ASKING",
    "STAGE_CONFIRM",
    "STAGE_NONE",
    "ask_message",
    "chip_list_text",
    "handle",
    "items_text",
    "parse_number_choice",
    "resolve_skills",
    "save",
    "start",
]
