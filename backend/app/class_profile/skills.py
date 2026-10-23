"""The closed list of teaching skills a teacher can say she wants to get better at.

`content/teaching_skills.yaml`: the ids are the one-on-one rubric criteria
(`content_models.ONE_ON_ONE_CRITERIA`) plus `other`, so the coach can lead with her skill and the
progress page can show before and after on it. Everything stored or classified is an id from this
file; each skill (except `other`) cites one handbook chunk. Hindi text is NFC-normalised at load.
"""

from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, field_validator

from backend.app.class_profile.library import CHUNKS_DIR, Citation, citations
from backend.app.config import settings
from backend.app.content_models import ONE_ON_ONE_CRITERIA, MoveCard
from backend.app.core.messages import get_ui_lang

SKILLS_PATH = Path(__file__).resolve().parents[3] / "content" / "teaching_skills.yaml"
OTHER_ID = "other"


def _nfc(value: Any) -> Any:
    return unicodedata.normalize("NFC", value).strip() if isinstance(value, str) else value


class TeachingSkill(BaseModel):
    id: str
    label_hi: str
    label_en: str
    chunk_id: str | None = None
    evidence: str | None = None  # a phrase that must occur in the chunk text (content test)

    _normalise = field_validator("label_hi", mode="after")(_nfc)

    @property
    def label(self) -> str:
        return self.label_en if get_ui_lang() == "en" else self.label_hi

    @property
    def is_rubric_criterion(self) -> bool:
        return self.id in ONE_ON_ONE_CRITERIA

    def citation(self) -> Citation | None:
        found = citations([self.chunk_id]) if self.chunk_id else []
        return found[0] if found else None


class SkillLibrary(BaseModel):
    skills: list[TeachingSkill]

    def ids(self) -> list[str]:
        return [s.id for s in self.skills]

    def get(self, skill_id: str) -> TeachingSkill | None:
        return next((s for s in self.skills if s.id == skill_id), None)

    def rubric_skills(self) -> list[TeachingSkill]:
        return [s for s in self.skills if s.is_rubric_criterion]


@lru_cache(maxsize=2)
def load_skills(path: str | None = None) -> SkillLibrary:
    source = Path(path) if path else SKILLS_PATH
    return SkillLibrary.model_validate(yaml.safe_load(source.read_text(encoding="utf-8")))


def clean_skill_ids(ids: list[str], lib: SkillLibrary | None = None) -> list[str]:
    """Only library ids, no repeats, in order, at most TEACHING_SKILLS_MAX.

    `other` is only kept on its own: it means "none of these", so it cannot sit next to a real skill.
    """
    lib = lib or load_skills()
    known = set(lib.ids())
    out: list[str] = []
    for sid in ids:
        if sid in known and sid not in out:
            out.append(sid)
    if OTHER_ID in out and len(out) > 1:
        out = [i for i in out if i != OTHER_ID]
    return out[: settings.TEACHING_SKILLS_MAX]


@lru_cache(maxsize=1)
def _chunk_texts() -> dict[str, str]:
    texts: dict[str, str] = {}
    for f in sorted(CHUNKS_DIR.glob("*.jsonl")):
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                texts[row["chunk_id"]] = unicodedata.normalize("NFC", row.get("text", ""))
    return texts


def validate_skills(lib: SkillLibrary) -> list[str]:
    """Problems found; empty = valid (run by the content test)."""
    errors: list[str] = []
    ids = lib.ids()
    if len(set(ids)) != len(ids):
        errors.append("duplicate skill id")
    expected = [*ONE_ON_ONE_CRITERIA, OTHER_ID]
    if ids != expected:
        errors.append(f"skill ids must be the rubric criteria then 'other': {expected}, got {ids}")
    for s in lib.skills:
        if not s.label_hi or not s.label_en:
            errors.append(f"{s.id}: missing label")
        if s.id == OTHER_ID:
            if s.chunk_id is not None:
                errors.append("other must not have a chunk (it is the handbook-tip-only entry)")
        elif s.citation() is None:
            errors.append(f"{s.id}: chunk {s.chunk_id!r} is not in content/chunks")
        elif not s.evidence:
            errors.append(f"{s.id}: no evidence phrase")
        elif not re.search(
            re.escape(unicodedata.normalize("NFC", s.evidence)), _chunk_texts()[s.chunk_id or ""]
        ):
            errors.append(f"{s.id}: evidence {s.evidence!r} not found in {s.chunk_id}")
    return errors


class SkillLevel(BaseModel):
    """How one chosen skill went in one scene: the rubric level and its plain-words descriptor."""

    skill_id: str
    level: int
    level_text_hi: str


def skill_levels(move: MoveCard, scores: dict[str, Any], skill_ids: list[str]) -> list[SkillLevel]:
    """The chosen skills that this scene's rubric scored, in her order (others are left out)."""
    if move.rubric_one_on_one is None:
        return []
    criteria = {c.id: c for c in move.rubric_one_on_one.criteria}
    out: list[SkillLevel] = []
    for sid in skill_ids:
        crit = criteria.get(sid)
        raw = scores.get(sid)
        if isinstance(raw, dict):
            raw = raw.get("score")
        if crit is None or not isinstance(raw, int) or isinstance(raw, bool):
            continue
        level = max(0, min(settings.SKILL_LEVEL_MAX, raw))
        out.append(
            SkillLevel(
                skill_id=sid,
                level=level,
                level_text_hi=unicodedata.normalize("NFC", crit.levels.get(level, "")),
            )
        )
    return out


class SkillView(BaseModel):
    """A skill as the My class page shows it: label in the UI language, and its handbook source."""

    id: str
    label: str
    source: str = ""  # "NISHTHA FLN, पृ. 435"; empty for `other`
    ocr: bool = False


def skill_views(ids: list[str], lib: SkillLibrary | None = None) -> list[SkillView]:
    lib = lib or load_skills()
    out: list[SkillView] = []
    for sid in ids:
        s = lib.get(sid)
        if s is None:
            continue
        cite = s.citation()
        out.append(
            SkillView(
                id=s.id,
                label=s.label,
                source=cite.label_hi() if cite else "",
                ocr=bool(cite and cite.ocr),
            )
        )
    return out


class SkillProgress(BaseModel):
    """Before and after on one chosen skill, from the scenes whose rubric scored it."""

    skill_id: str
    label: str
    n_scenes: int
    ready: bool  # enough scenes (SKILL_PROGRESS_MIN_SCENES) to show a before and after
    first_level: int | None = None
    first_text_hi: str = ""
    last_level: int | None = None
    last_text_hi: str = ""


def skill_progress(
    scored: list[tuple[str, dict[str, Any]]],
    skill_ids: list[str],
    lib: SkillLibrary | None = None,
) -> list[SkillProgress]:
    """`scored` is (move_id, coach scores) per scene, oldest first. Only rubric skills are shown."""
    from backend.app.rehearsal.scene_runner import load_move_card

    lib = lib or load_skills()
    out: list[SkillProgress] = []
    for sid in skill_ids:
        skill = lib.get(sid)
        if skill is None or not skill.is_rubric_criterion:
            continue
        levels: list[SkillLevel] = []
        for move_id, scores in scored:
            try:
                move = load_move_card(move_id)
            except (FileNotFoundError, ValueError):
                continue
            levels.extend(skill_levels(move, scores, [sid]))
        ready = len(levels) >= settings.SKILL_PROGRESS_MIN_SCENES
        first, last = (levels[0], levels[-1]) if levels else (None, None)
        out.append(
            SkillProgress(
                skill_id=sid,
                label=skill.label,
                n_scenes=len(levels),
                ready=ready,
                first_level=first.level if ready and first else None,
                first_text_hi=first.level_text_hi if ready and first else "",
                last_level=last.level if ready and last else None,
                last_text_hi=last.level_text_hi if ready and last else "",
            )
        )
    return out
