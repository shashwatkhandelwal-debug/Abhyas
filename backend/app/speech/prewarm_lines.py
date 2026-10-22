"""Hindi lines the demo can speak without any LLM call, for TTS prewarming (scripts/prewarm_tts.py).

Every line here is fixed text with a fixed voice, so its cache key is known ahead of time:

- catalog messages marked ``audio: true`` that have no ``{placeholders}`` (welcome, consent, ...),
  both the feminine and the ``text_m`` variant, plus the coach-voiced scene end lines;
- each move's ``learn_script_hi`` and its scripted ``model_rehearsal`` lines;
- each persona's scripted ``off_topic_lines_hi`` (and the "सर" variant);
- the children's deterministic *template* lines (``template_line``) for every demo move, collected
  by replaying scripted teacher turns through the real rule engine with the LLM switched off.

Lines the LLM writes (child voice with a live key, coach feedback with the teacher's own words,
guide answers) are not predictable and are not prewarmed.
"""

from __future__ import annotations

import importlib
import logging
import unicodedata
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger("abhyas.speech.prewarm_lines")

REPO_ROOT = Path(__file__).resolve().parents[3]

# (label, text_hi, voice_id)
Target = tuple[str, str, str]

# Catalog messages the coach speaks (scene_runner posts them with speaker="coach")
COACH_CATALOG_KEYS = ("scene_all_correct", "scene_ended_neutral")
# Teacher turns that exercise the engine for every demo move, besides the move's own scripted
# model_rehearsal turns: an ask-to-explain + concrete-material run, and a tell-the-answer run.
GOOD_TEACHER_TURNS = (
    "रवि, तुमने कैसे घटाया? मुझे समझाओ",
    "तीलियाँ और बंडल खोलकर बताओ",
    "शाबाश, 10 का बंडल खोलो",
)
TELL_TEACHER_TURNS = (
    "रवि, इसका उत्तर 16 है, कॉपी में 16 लिख दो",
    "चलो 16 लिख दिया",
    "अब प्रिया, तुम बताओ",
)
SCRIPT_ADDRESS_FORMS = ("f", "m")


def _nfc(text: str) -> str:
    return unicodedata.normalize("NFC", text.strip())


def _is_fixed(text: str) -> bool:
    return bool(text) and not ("{" in text and "}" in text)


def catalog_targets(messages_path: Path) -> list[Target]:
    """Fixed catalog messages with audio: true (plus the coach scene-end lines)."""
    targets: list[Target] = []
    if not messages_path.is_file():
        return targets
    content: dict[str, Any] = yaml.safe_load(messages_path.read_text(encoding="utf-8")) or {}
    for key, val in content.items():
        if not isinstance(val, dict):
            continue
        if not val.get("audio") and key not in COACH_CATALOG_KEYS:
            continue
        voice = "coach" if key in COACH_CATALOG_KEYS else "abhyas"
        for field_name in ("text", "text_m"):
            txt = val.get(field_name)
            if isinstance(txt, str) and _is_fixed(txt):
                targets.append((f"msg:{key}:{field_name}", _nfc(txt), voice))
    return targets


def move_targets(moves_dir: Path, personas: dict[str, str]) -> list[Target]:
    """learn_script_hi and scripted model_rehearsal lines (teacher -> model_teacher voice)."""
    targets: list[Target] = []
    if not moves_dir.is_dir():
        return targets
    for move_file in sorted(moves_dir.glob("*.yaml")):
        try:
            data = yaml.safe_load(move_file.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError) as exc:
            logger.warning("Failed loading move from %s: %s", move_file, exc)
            continue
        learn = data.get("learn_script_hi")
        if isinstance(learn, str) and learn.strip():
            targets.append((f"move:{move_file.stem}:learn", _nfc(learn), "abhyas"))
        for idx, line in enumerate(data.get("model_rehearsal") or []):
            if not isinstance(line, dict) or not isinstance(line.get("text_hi"), str):
                continue
            speaker = str(line.get("speaker", "teacher"))
            voice = "model_teacher" if speaker == "teacher" else personas.get(speaker)
            if voice:
                targets.append((f"move:{move_file.stem}:model:{idx}", _nfc(line["text_hi"]), voice))
    return targets


def persona_targets(personas_dir: Path) -> tuple[list[Target], dict[str, str]]:
    """Scripted off-topic lines per child, and the persona-id -> voice-id map."""
    targets: list[Target] = []
    voices: dict[str, str] = {}
    if not personas_dir.is_dir():
        return targets, voices
    for pf in sorted(personas_dir.glob("*.yaml")):
        try:
            data = yaml.safe_load(pf.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError) as exc:
            logger.warning("Failed loading persona from %s: %s", pf, exc)
            continue
        pid, voice = str(data.get("id", pf.stem)), str(data.get("voice_id", ""))
        if not voice:
            continue
        voices[pid] = voice
        for idx, line in enumerate(data.get("off_topic_lines_hi") or []):
            variants = {_nfc(line), _nfc(line.replace("दीदी", "सर").replace("मैडम", "सर"))}
            for v_idx, text in enumerate(sorted(variants)):
                targets.append((f"persona:{pid}:off_topic:{idx}:{v_idx}", text, voice))
    return targets, voices


async def engine_template_targets(moves_dir: Path) -> list[Target]:
    """Template child lines the rule engine produces for each demo move's scripted turns.

    The real SceneRunner runs with the LLM off and ``voice_child_line`` replaced by the
    deterministic ``template_line``, so what is collected is exactly what the product says when
    the child-voice model is unavailable.
    """
    # Imported here: they pull in the rehearsal stack, which the plain catalog path does not need
    from backend.app.llm.roles import act_tagger, child_voice

    sr: Any = importlib.import_module("backend.app.rehearsal.scene_runner")  # patched below
    from backend.app.rehearsal.scene_store import SceneStore
    from backend.app.speech.tts import MockTTS

    if not moves_dir.is_dir():
        return []
    collected: dict[tuple[str, str], str] = {}
    original_voice, original_tag = sr.voice_child_line, sr.tag_act
    persona_cards = sr.load_personas()

    async def template_only(
        response: Any,
        persona: Any,
        last_4_lines: list[str] | None = None,
        turn_idx: int = 0,
        address_form: str = "f",
    ) -> str:
        return child_voice.template_line(
            response=response, persona=persona, turn_idx=turn_idx, address_form=address_form
        )

    async def keyword_tagger(*, transcript: str, **kwargs: Any) -> Any:
        return act_tagger.fallback_tag_act(
            transcript,
            scene_persona_ids=kwargs.get("scene_persona_ids"),
            current_item=kwargs.get("current_item"),
        )

    sr.voice_child_line = template_only  # no LLM, and nothing is written to llm_call
    sr.tag_act = keyword_tagger
    try:
        runner = sr.SceneRunner(tts_provider=MockTTS(), store=SceneStore(), personas=persona_cards)
        from uuid import uuid4

        for move_file in sorted(moves_dir.glob("*.yaml")):
            data = yaml.safe_load(move_file.read_text(encoding="utf-8")) or {}
            move_id = str(data.get("id", move_file.stem))
            scripted = [
                str(m["text_hi"])
                for m in data.get("model_rehearsal") or []
                if isinstance(m, dict) and m.get("speaker") == "teacher" and m.get("text_hi")
            ]
            for script in (scripted, list(GOOD_TEACHER_TURNS), list(TELL_TEACHER_TURNS)):
                for form in SCRIPT_ADDRESS_FORMS:
                    try:
                        rec = await runner.create_scene(uuid4(), move_id=move_id)
                        for text in script:
                            res = await runner.turn(
                                rec.scene_id, text, address_form=form, synthesize_audio=False
                            )
                            for cl in res.turn.child_lines:
                                if cl.line_hi.strip():
                                    collected[(cl.voice_id, _nfc(cl.line_hi))] = (
                                        f"engine:{move_id}:{cl.persona_id}"
                                    )
                            if res.turn.ended:
                                break
                    except (ValueError, KeyError) as exc:
                        logger.warning("Replay failed for move %s: %s", move_id, exc)
                        break
    finally:
        sr.voice_child_line, sr.tag_act = original_voice, original_tag
    return [(label, text, voice) for (voice, text), label in sorted(collected.items())]


async def build_prewarm_targets(
    messages_path: Path | None = None,
    moves_dir: Path | None = None,
    personas_dir: Path | None = None,
    *,
    include_engine_lines: bool = True,
) -> list[Target]:
    """All fixed lines, de-duplicated by (voice, text), in a stable order."""
    messages = messages_path or REPO_ROOT / "content" / "messages_hi.yaml"
    moves = moves_dir or REPO_ROOT / "content" / "moves"
    personas_path = personas_dir or REPO_ROOT / "content" / "personas"

    persona_lines, voices = persona_targets(personas_path)
    targets = [
        *catalog_targets(messages),
        *move_targets(moves, voices),
        *persona_lines,
    ]
    if include_engine_lines:
        targets.extend(await engine_template_targets(moves))

    seen: set[tuple[str, str]] = set()
    unique: list[Target] = []
    for label, text, voice in targets:
        if (voice, text) in seen:
            continue
        seen.add((voice, text))
        unique.append((label, text, voice))
    return unique
