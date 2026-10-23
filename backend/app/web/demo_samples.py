"""Sample lines for the demo ("Try a sample line: tap to send"), chosen for where she is.

A sample is offered only where it makes sense (see content/demo_samples.yaml): the lines about a
child's answer only inside a scene, the diagnosis line only at the diagnose step, and so on. The
lines that depend on the scene are built from the board's own item and the move card, never
invented: the "new problem" is the next problem on the card that needs regrouping.
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from backend.app.config import settings
from backend.app.core.messages import get_message, get_ui_lang
from backend.app.rehearsal.scene_runner import load_move_card

logger = logging.getLogger("abhyas.web.demo_samples")
SAMPLES_FILE = Path(__file__).resolve().parents[3] / "content" / "demo_samples.yaml"


@lru_cache(maxsize=1)
def _load() -> tuple[dict[str, Any], ...]:
    data = yaml.safe_load(SAMPLES_FILE.read_text(encoding="utf-8"))
    return tuple(data["samples"])


def needs_regrouping(item: dict[str, Any]) -> bool:
    """Does this problem need the move's idea (opening a bundle, or making a new one)?"""
    a, b = item.get("a"), item.get("b")
    if item.get("type") == "sub" and a is not None and b is not None:
        return int(a) % 10 < int(b) % 10
    if item.get("type") == "add" and a is not None and b is not None:
        return int(a) % 10 + int(b) % 10 >= 10
    return False


def next_problem(move_id: str, current: dict[str, Any]) -> dict[str, Any] | None:
    """The next item on the move card after `current` that needs regrouping (else the next item)."""
    try:
        items = list(load_move_card(move_id).scenario.items)
    except (FileNotFoundError, ValueError):
        return None

    def same(raw: dict[str, Any]) -> bool:
        keys = ("type", "a", "b", "tens", "ones", "word")
        return all(raw.get(k) == current.get(k) for k in keys if current.get(k) is not None)

    at = next((i for i, raw in enumerate(items) if same(raw)), -1)
    after = items[at + 1 :] + items[: max(at, 0)]
    for raw in after:
        if needs_regrouping(raw):
            return raw
    return after[0] if after else None


def _answer(item: dict[str, Any]) -> int | None:
    a, b = item.get("a"), item.get("b")
    if a is None or b is None:
        return None
    return int(a) - int(b) if item.get("type") == "sub" else int(a) + int(b)


def _text(
    sample: dict[str, Any], item: dict[str, Any] | None, child_hi: str, move_id: str
) -> str | None:
    """The Hindi line to send, or None when this sample has nothing to say for this item."""
    kind = sample["text_kind"]
    if kind == "static":
        return str(sample["text_hi"])
    if item is None:
        return None
    kind_of_item = str(item.get("type"))
    if kind == "ask_how":
        key = {
            "sub": "hint_example_sub",
            "add": "hint_example_add",
            "place_value": "hint_example_place_value",
            "read_word": "hint_example_read",
        }.get(kind_of_item)
        if key is None:
            return None
        line = get_message(key, lang="hi", child=child_hi, a=item.get("a"), b=item.get("b"))
        return line + str(sample.get("text_suffix_hi", ""))
    if kind == "tell_answer":
        if kind_of_item == "read_word":
            return str(sample["text_tpl_read_word"]).format(word=item.get("word"))
        answer = _answer(item)
        return None if answer is None else str(sample["text_tpl"]).format(answer=answer)
    if kind == "new_problem":
        fresh = next_problem(move_id, item)
        template = sample.get(f"text_tpl_{kind_of_item}")
        if fresh is None or template is None:
            return None
        return str(template).format(
            new_a=fresh.get("a"), new_b=fresh.get("b"), new_word=fresh.get("word")
        )
    return None


def build_samples(
    *,
    state: str,
    stage: str,
    scene: dict[str, Any] | None,
    move_id: str,
    audio: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """The samples to show now: {id, label, note, text, audio} in the UI language.

    `audio` maps a sample id to the Hindi text its rendered voice note says; a sample whose text
    matches it can be sent as that voice note.
    """
    lang = get_ui_lang()
    in_scene = scene is not None and state in ("REHEARSE_INTRO", "REHEARSE") and stage != "diagnose"
    scopes = {"any"}
    if in_scene:
        scopes.add("scene")
    if state in ("REHEARSE_INTRO", "REHEARSE") and stage == "diagnose":
        scopes.add("diagnose")
    if state == "EXPLAIN_BACK":
        scopes.add("explain_back")
    item = (scene or {}).get("item")
    if scene is None:
        child, child_hi = "", ""
    elif scene.get("mode") == "one_on_one":
        child = str(scene.get("child_name", ""))
        child_hi = get_message(f"speaker_{scene.get('child_id', 'ravi')}", lang="hi")
    else:
        children = scene.get("children") or []
        child = str(children[0]["name"]) if children else ""
        child_hi = get_message(f"speaker_{children[0]['id']}", lang="hi") if children else ""
    out: list[dict[str, Any]] = []
    for sample in _load():
        if sample["scope"] not in scopes:
            continue
        text = _text(sample, item, child_hi, move_id)
        if not text:
            continue
        fills = {"child": child or get_message("speaker_ravi")}
        out.append(
            {
                "id": sample["id"],
                "label": str(sample["label"][lang]).format(**fills),
                "note": str(sample["note"][lang]).format(**fills),
                "text": text,
                "audio": bool(audio and audio.get(sample["id"]) == text),
            }
        )
    return out


def load_demo_chips() -> list[dict[str, Any]]:
    """The evaluator voice samples (eval/samples/demo_chips.json), with `audio_available` computed
    from the rendered file; only when DEMO_MODE is on. The page uses them for audio, not for text."""
    if not settings.DEMO_MODE:
        return []
    samples_dir = Path(__file__).resolve().parents[3] / "eval" / "samples"
    path = samples_dir / "demo_chips.json"
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        logger.warning("Failed to read %s", path, exc_info=True)
        return []
    if not isinstance(data, list):
        return []
    from backend.app.speech.audio import is_wav_non_silent

    for item in data:
        if isinstance(item, dict):
            wav = samples_dir / "audio" / f"{item.get('id')}.wav"
            item["audio_available"] = bool(
                item.get("id") and wav.is_file() and is_wav_non_silent(wav)
            )
    return [i for i in data if isinstance(i, dict)]


def demo_sample_audio() -> dict[str, str]:
    """Sample id -> the Hindi text its rendered voice note says (only samples with real audio)."""
    return {
        str(c["id"]): str(c["text_hi"])
        for c in load_demo_chips()
        if c.get("audio_available") and c.get("id") and c.get("text_hi")
    }
