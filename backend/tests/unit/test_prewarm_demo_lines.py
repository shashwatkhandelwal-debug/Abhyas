"""Prewarm target list for the demo's fixed Hindi lines and the paced, idempotent run (mock TTS)."""

import re
from pathlib import Path

import pytest

import scripts.prewarm_tts as prewarm_script
from backend.app.speech.cache import TTSCache
from backend.app.speech.prewarm_lines import build_prewarm_targets
from backend.app.speech.tts import MockTTS
from scripts.prewarm_tts import prewarm_tts


@pytest.fixture(scope="module")
async def targets() -> list[tuple[str, str, str]]:
    return await build_prewarm_targets()


async def test_targets_cover_every_fixed_speaker(targets: list[tuple[str, str, str]]) -> None:
    voices = {voice for _label, _text, voice in targets}
    assert {
        "abhyas",
        "coach",
        "model_teacher",
        "child_ravi",
        "child_priya",
        "child_aman",
    } <= voices
    kinds = {label.split(":")[0] for label, _t, _v in targets}
    assert {"msg", "move", "persona", "engine"} <= kinds


async def test_targets_are_fixed_unique_and_hindi(targets: list[tuple[str, str, str]]) -> None:
    assert len(targets) >= 60
    assert len({(v, t) for _l, t, v in targets}) == len(targets)
    for label, text, _voice in targets:
        assert "{" not in text and "}" not in text, label
        assert re.search(r"[ऀ-ॿ0-9]", text), label


async def test_welcome_and_consent_prompts_are_prewarmed(
    targets: list[tuple[str, str, str]],
) -> None:
    labels = {label for label, _t, _v in targets}
    assert {"msg:welcome:text", "msg:consent_service:text", "msg:scene_all_correct:text"} <= labels
    coach = {label for label, _t, v in targets if v == "coach"}
    assert "msg:scene_all_correct:text" in coach


async def test_run_is_capped_paced_and_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # an empty private cache, so the counts do not depend on earlier runs
    monkeypatch.setattr(prewarm_script, "tts_cache", TTSCache(cache_dir=tmp_path, use_db=False))
    first = await prewarm_tts(
        tts_provider=MockTTS(),
        force_mock=True,
        include_demo_lines=True,
        request_interval_s=0.0,
        max_synth=4,
    )
    assert first["synthesized"] == 4
    assert first["tts_calls"] >= 4

    second = await prewarm_tts(
        tts_provider=MockTTS(),
        force_mock=True,
        include_demo_lines=True,
        request_interval_s=0.0,
        max_synth=4,
    )
    assert second["already_cached"] >= first["synthesized"]
    assert second["synthesized"] == 4  # continued with the next four, did not redo the first


def test_start_script_prewarms_in_background_after_seed_and_before_uvicorn() -> None:
    script = (Path(__file__).resolve().parents[3] / "scripts" / "start.sh").read_text("utf-8")
    seed, prewarm, serve = (
        script.index("SEED_ON_BOOT"),
        script.index("PREWARM_ON_BOOT"),
        script.index("exec uvicorn"),
    )
    assert seed < prewarm < serve
    block = script[prewarm:serve]
    assert 'PREWARM_ON_BOOT:-false}" = "true"' in block  # off unless explicitly enabled
    assert "scripts/prewarm_tts.py" in block and ") &" in block  # background, never blocks
