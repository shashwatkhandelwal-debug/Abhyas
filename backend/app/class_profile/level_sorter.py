"""The level sorter: "Group my class by level".

She picks reading or maths, then taps a rough count of children per level (0, 1-5, 6-10, 11-20, 20+).
Out comes a short plan: two or three groups, which group to sit with first, and one 10-minute
activity per group. Every activity is a stored paraphrase of handbook chunks, cited by those chunks
(`content/level_sorter.yaml`); a level with no stored chunk says so instead of inventing one.

No names and no per-child data are asked for or stored. The tapped ranges live on `SessionContext`
for this conversation only and are cleared when the plan is shown. Nothing here calls an LLM.
Buttons are catalog keys (`btn_lvl_*`); the WhatsApp channel turns a screen of more than 3 options
into an interactive list (`channels/whatsapp/buttons.py`).
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator

from backend.app.class_profile.library import CONTENT_DIR, citations
from backend.app.class_profile.library import Citation as StoredCitation
from backend.app.config import settings
from backend.app.core.intents import Intent
from backend.app.core.messages import get_message, get_ui_lang
from backend.app.core.types import Button, Citation, OutboundMessage
from backend.app.llm.roles.guide_answerer import format_guide_citation
from backend.app.sessions.state_machine import SessionContext, SessionStateEnum
from backend.app.sessions.training_rating import is_rating_escape

SORTER_PATH = CONTENT_DIR / "level_sorter.yaml"

STAGE_NONE = ""
STAGE_SUBJECT = "subject"
STAGE_COUNT = "count"
STAGE_RESULT = "result"

BTN_START = "btn_lvl_start"
BTN_HANDBOOK = "btn_lvl_handbook"
BTN_RESUME = "btn_lvl_resume"
SUBJECT_PREFIX = "btn_lvl_sub_"
COUNT_PREFIX = "btn_lvl_cnt_"

_TRAILING = " .!?।,"
_SCENE_SETUP = SessionStateEnum.REHEARSE_INTRO  # picking the child: not available here
_SCENE = SessionStateEnum.REHEARSE  # a running scene: paused, never touched


def _nfc(value: Any) -> Any:
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value).strip()
    return value


class Level(BaseModel):
    activity_hi: str
    activity_en: str
    chunk_ids: list[str] = Field(default_factory=list, max_length=2)

    _normalise = field_validator("activity_hi", mode="after")(_nfc)


class Multigrade(BaseModel):
    chunk_ids: list[str] = Field(min_length=1)
    text_hi: str
    text_en: str

    _normalise = field_validator("text_hi", mode="after")(_nfc)


class Subject(BaseModel):
    levels: list[str] = Field(min_length=2)  # lowest (most support) first
    first_chunk_ids: list[str] = Field(default_factory=list)
    multigrade: Multigrade | None = None


class SorterContent(BaseModel):
    subjects: dict[str, Subject]
    levels: dict[str, Level]


@lru_cache(maxsize=2)
def load_content(path: str | None = None) -> SorterContent:
    source = Path(path) if path else SORTER_PATH
    return SorterContent.model_validate(yaml.safe_load(source.read_text(encoding="utf-8")))


@dataclass(frozen=True)
class Group:
    levels: tuple[str, ...]  # one level, or two neighbouring levels merged (lowest first)


def bucket_count(bucket: str) -> int:
    return settings.LEVEL_BUCKET_COUNTS.get(bucket, 0)


def plan_groups(levels: list[str], counts: dict[str, str]) -> list[Group]:
    """Groups for the levels that have children, lowest level first.

    Every non-empty level is a group; while there are more than `LEVEL_MAX_GROUPS`, the two
    neighbouring groups with the fewest children together are merged (the lower pair on a tie).
    Pure and deterministic.
    """
    groups = [[lv] for lv in levels if bucket_count(counts.get(lv, "0")) > 0]
    while len(groups) > settings.LEVEL_MAX_GROUPS:
        size = [sum(bucket_count(counts.get(lv, "0")) for lv in g) for g in groups]
        pair = min(range(len(groups) - 1), key=lambda i: (size[i] + size[i + 1], i))
        groups[pair : pair + 2] = [groups[pair] + groups[pair + 1]]
    return [Group(tuple(g)) for g in groups]


@dataclass
class LevelResult:
    messages: list[OutboundMessage] = field(default_factory=list)
    handled: bool = True
    handbook: bool = False  # carry on as the handbook-question button
    resume_scene: bool = False  # back to the paused scene (the service says where she was)


def _btn(button_id: str) -> Button:
    return Button(id=button_id, title_hi=get_message(button_id)[: settings.WEB_BUTTON_TITLE_MAX])


def subject_label(subject: str) -> str:
    return get_message(f"lvl_subject_{subject}")


def level_label(level: str) -> str:
    return get_message(f"lvl_label_{level}")


def count_label(bucket: str) -> str:
    return get_message(f"lvl_count_label_{bucket}")


def _sources(chunk_ids: list[str], address_form: str) -> tuple[str, list[Citation]]:
    """One citation line and chip per stored chunk (a chunk that is not stored is skipped)."""
    found: list[StoredCitation] = citations(chunk_ids)
    lines: list[str] = []
    cites: list[Citation] = []
    for c in found:
        line = format_guide_citation(c.source_short_hi, c.page, address_form=address_form)
        lines.append(line)
        cites.append(
            Citation(
                chunk_id=c.chunk_id, source_short_hi=c.source_short_hi, page=c.page, line_hi=line
            )
        )
    return "\n".join(lines), cites


def _subject_screen(ctx: SessionContext) -> OutboundMessage:
    ctx.level_stage = STAGE_SUBJECT
    ctx.level_subject = ""
    ctx.level_idx = 0
    ctx.level_counts = {}
    return OutboundMessage(
        kind="buttons",
        text_hi=get_message("lvl_subject_ask"),
        buttons=[_btn(f"{SUBJECT_PREFIX}{s}") for s in load_content().subjects],
    )


def _count_screen(ctx: SessionContext, content: SorterContent) -> OutboundMessage:
    ctx.level_stage = STAGE_COUNT
    levels = content.subjects[ctx.level_subject].levels
    return OutboundMessage(
        kind="buttons",
        text_hi=get_message(
            "lvl_count_ask",
            subject=subject_label(ctx.level_subject),
            level=level_label(levels[ctx.level_idx]),
            step=ctx.level_idx + 1,
            total=len(levels),
        ),
        buttons=[_btn(f"{COUNT_PREFIX}{b}") for b in settings.LEVEL_BUCKET_COUNTS],
    )


def _screen(ctx: SessionContext, content: SorterContent, *, note: bool = False) -> OutboundMessage:
    """The screen for the current stage (shown again when she types instead of tapping)."""
    msg = (
        _count_screen(ctx, content)
        if ctx.level_stage == STAGE_COUNT and ctx.level_subject in content.subjects
        else _subject_screen(ctx)
    )
    if note:
        msg = msg.model_copy(update={"text_hi": f"{get_message('lvl_pick_button')}\n{msg.text_hi}"})
    return msg


def _group_levels_text(group: Group, counts: dict[str, str]) -> str:
    return " + ".join(
        f"{level_label(lv)} ({count_label(counts.get(lv, '0'))})" for lv in group.levels
    )


def result_messages(
    ctx: SessionContext, content: SorterContent | None = None
) -> list[OutboundMessage]:
    """The plan: heading, the group to sit with first, then one activity per group."""
    content = content or load_content()
    subject = content.subjects[ctx.level_subject]
    counts = ctx.level_counts
    groups = plan_groups(subject.levels, counts)
    lang_en = get_ui_lang() == "en"
    minutes = settings.LEVEL_ACTIVITY_MINUTES
    if not groups:
        return [
            OutboundMessage(
                kind="buttons",
                text_hi=get_message("lvl_empty"),
                buttons=[_btn(BTN_START)],
            )
        ]

    head_key = "lvl_head_one" if len(groups) == 1 else "lvl_head_many"
    head = get_message(head_key, subject=subject_label(ctx.level_subject), n=len(groups))
    if len(groups) > 1:
        sources, head_cites = _sources(subject.first_chunk_ids, ctx.address_form)
        head += "\n" + get_message("lvl_first", sources=sources).rstrip()
    else:
        head_cites = []
    if any(len(g.levels) > 1 for g in groups):
        head += "\n" + get_message("lvl_merged_note")
    out = [OutboundMessage(kind="text", text_hi=head, citations=head_cites)]

    for n, group in enumerate(groups, start=1):
        level = content.levels[group.levels[0]]
        sources, cites = _sources(level.chunk_ids, ctx.address_form)
        title = _group_levels_text(group, counts)
        if cites:
            text = get_message(
                "lvl_group",
                n=n,
                levels=title,
                minutes=minutes,
                activity=level.activity_en if lang_en else level.activity_hi,
                sources=sources,
            )
        else:
            text = get_message("lvl_group_missing", n=n, levels=title)
        out.append(OutboundMessage(kind="text", text_hi=text, citations=cites))

    if subject.multigrade is not None:
        sources, cites = _sources(subject.multigrade.chunk_ids, ctx.address_form)
        if cites:
            line = subject.multigrade.text_en if lang_en else subject.multigrade.text_hi
            out.append(
                OutboundMessage(
                    kind="text",
                    text_hi=get_message("lvl_multigrade", text=line, sources=sources),
                    citations=cites,
                )
            )

    if ctx.current_state == _SCENE:  # the scene is paused: offer the way back
        tail = OutboundMessage(
            kind="buttons",
            text_hi=get_message("lvl_scene_waiting"),
            buttons=[_btn(BTN_RESUME), _btn(BTN_HANDBOOK)],
        )
    else:
        tail = OutboundMessage(
            kind="buttons", text_hi=get_message("lvl_after"), buttons=[_btn(BTN_HANDBOOK)]
        )
    out.append(tail)
    return out


def is_level_command(text: str) -> bool:
    cleaned = unicodedata.normalize("NFC", text or "").strip(_TRAILING).strip().lower()
    if not cleaned:
        return False
    for lang in ("hi", "en"):
        raw = get_message("lvl_command_words", lang=lang)
        words = {unicodedata.normalize("NFC", w).strip().lower() for w in raw.split(",")}
        if cleaned in words:
            return True
    return False


def reset(ctx: SessionContext) -> None:
    ctx.level_stage = STAGE_NONE
    ctx.level_subject = ""
    ctx.level_idx = 0
    ctx.level_counts = {}


def start(ctx: SessionContext) -> LevelResult:
    reset(ctx)
    return LevelResult([_subject_screen(ctx)])


def handle(
    ctx: SessionContext,
    text: str,
    button_id: str | None,
    intent: Intent | None,
    content: SorterContent | None = None,
) -> LevelResult:
    """One inbound message. `handled=False` means "not mine, carry on with normal routing"."""
    content = content or load_content()
    text = (text or "").strip()
    in_setup = ctx.current_state == _SCENE_SETUP
    in_scene = ctx.current_state == _SCENE

    if button_id == BTN_START:  # also works inside a running scene (it is paused)
        return LevelResult(handled=False) if in_setup else start(ctx)
    if ctx.level_stage == STAGE_NONE and not button_id and is_level_command(text):
        # typed words inside a scene are her line to the child, never a command
        return LevelResult(handled=False) if in_setup or in_scene else start(ctx)

    if button_id == BTN_RESUME and in_scene:
        reset(ctx)
        return LevelResult(resume_scene=True)

    is_level_button = bool(button_id) and str(button_id).startswith("btn_lvl_")
    if ctx.level_stage == STAGE_NONE:
        if is_level_button:  # a button from an earlier, finished plan
            return LevelResult([OutboundMessage(kind="text", text_hi=get_message("lvl_already"))])
        return LevelResult(handled=False)

    if ctx.level_stage == STAGE_RESULT:
        if button_id == BTN_HANDBOOK:
            reset(ctx)
            return LevelResult(handbook=True, handled=False)
        if is_level_button:  # the same tap twice, or an old button
            return LevelResult([OutboundMessage(kind="text", text_hi=get_message("lvl_already"))])
        reset(ctx)
        return LevelResult(handled=False)

    if not button_id:
        if not text or in_scene or is_rating_escape(intent, text):
            # a command ends the sorter and runs normally; inside a paused scene her typing is the
            # next line to the child, so the unfinished sorter is dropped (nothing was stored)
            reset(ctx)
            return LevelResult(handled=False)
        return LevelResult([_screen(ctx, content, note=True)])

    if ctx.level_stage == STAGE_SUBJECT and button_id.startswith(SUBJECT_PREFIX):
        subject = button_id[len(SUBJECT_PREFIX) :]
        if subject in content.subjects:
            ctx.level_subject = subject
            ctx.level_idx = 0
            ctx.level_counts = {}
            return LevelResult([_count_screen(ctx, content)])

    elif ctx.level_stage == STAGE_COUNT and button_id.startswith(COUNT_PREFIX):
        bucket = button_id[len(COUNT_PREFIX) :]
        subject_levels = content.subjects[ctx.level_subject].levels
        if bucket in settings.LEVEL_BUCKET_COUNTS and ctx.level_idx < len(subject_levels):
            ctx.level_counts = {**ctx.level_counts, subject_levels[ctx.level_idx]: bucket}
            ctx.level_idx += 1
            if ctx.level_idx < len(subject_levels):
                return LevelResult([_count_screen(ctx, content)])
            messages = result_messages(ctx, content)
            if any(b > 0 for b in map(bucket_count, ctx.level_counts.values())):
                ctx.level_stage = STAGE_RESULT
            else:
                reset(ctx)  # nothing to group: the empty message offers a fresh start
            ctx.level_counts = {}
            return LevelResult(messages)

    return LevelResult([_screen(ctx, content, note=True)])  # not a button of this screen


def validate_content(content: SorterContent | None = None) -> list[str]:
    """Problems found; empty = valid. Run by the content test."""
    from backend.app.class_profile.library import _chunk_index

    content = content or load_content()
    index = _chunk_index()
    errors: list[str] = []
    used: set[str] = set()
    for sid, subject in content.subjects.items():
        used.update(subject.levels)
        for lv in subject.levels:
            if lv not in content.levels:
                errors.append(f"{sid}: level {lv} has no entry")
        ids = list(subject.first_chunk_ids)
        if subject.multigrade:
            ids += subject.multigrade.chunk_ids
        errors += [f"{sid}: chunk {c} is not stored" for c in ids if c not in index]
    for lv, level in content.levels.items():
        if lv not in used:
            errors.append(f"level {lv} is in no subject")
        errors += [f"{lv}: chunk {c} is not stored" for c in level.chunk_ids if c not in index]
    return errors


__all__ = [
    "BTN_HANDBOOK",
    "BTN_RESUME",
    "BTN_START",
    "Group",
    "LevelResult",
    "handle",
    "is_level_command",
    "load_content",
    "plan_groups",
    "reset",
    "result_messages",
    "start",
    "validate_content",
]
