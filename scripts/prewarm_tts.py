"""Static TTS Audio Pre-warming CLI Script (Task T63, spec/06 §6.3, spec/12 §12.3).

Synthesizes and caches fixed catalog messages with audio: true and move learn narration.
- Idempotent: Skips lines already present in tts_cache.
- Budget-capped: Respects SPEECH_DAILY_BUDGET_INR and SPEECH_TOTAL_BUDGET_INR.
- Mock-aware: No-op when running against MockTTS unless --force-mock is passed.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import unicodedata
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

# Rule C justification: CLI script runs standalone; sys.path configured before app imports
from backend.app.config import settings  # noqa: E402
from backend.app.speech.audio import to_wav  # noqa: E402
from backend.app.speech.cache import compute_cache_key, tts_cache  # noqa: E402
from backend.app.speech.spend import calculate_tts_cost, speech_budget  # noqa: E402
from backend.app.speech.tts import TTSProvider, get_tts_provider  # noqa: E402
from backend.app.speech.voices import get_voice  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("abhyas.scripts.prewarm_tts")


def load_prewarm_targets(
    messages_path: Path,
    moves_dir: Path,
) -> list[tuple[str, str, str]]:
    """Loads all fixed text targets to pre-warm.

    Returns:
        List of tuples: (target_label, text_hi, voice_id)
    """
    targets: list[tuple[str, str, str]] = []

    # 1. Catalog messages marked audio: true
    if messages_path.is_file():
        try:
            content = yaml.safe_load(messages_path.read_text(encoding="utf-8")) or {}
            for key, val in content.items():
                if not isinstance(val, dict) or not val.get("audio"):
                    continue
                for field_name in ("text", "text_m"):
                    txt = val.get(field_name)
                    if not txt or not isinstance(txt, str):
                        continue
                    # Skip dynamic format string templates
                    if "{" in txt and "}" in txt:
                        continue
                    clean_txt = unicodedata.normalize("NFC", txt.strip())
                    if clean_txt:
                        targets.append((f"msg:{key}:{field_name}", clean_txt, "abhyas"))
        except Exception as exc:
            logger.warning("Failed loading messages from %s: %s", messages_path, exc)

    # 2. Move learn scripts
    if moves_dir.is_dir():
        for move_file in sorted(moves_dir.glob("*.yaml")):
            try:
                m_data = yaml.safe_load(move_file.read_text(encoding="utf-8")) or {}
                learn_script = m_data.get("learn_script_hi")
                if learn_script and isinstance(learn_script, str):
                    clean_script = unicodedata.normalize("NFC", learn_script.strip())
                    if clean_script:
                        targets.append((f"move:{move_file.stem}:learn", clean_script, "abhyas"))
            except Exception as exc:
                logger.warning("Failed loading move from %s: %s", move_file, exc)

    return targets


async def prewarm_tts(
    messages_path: Path = REPO_ROOT / "content" / "messages_hi.yaml",
    moves_dir: Path = REPO_ROOT / "content" / "moves",
    tts_provider: TTSProvider | None = None,
    force_mock: bool = False,
    dry_run: bool = False,
) -> dict[str, int | float]:
    """Executes TTS pre-warming for fixed audio prompts."""
    # Check if mock mode is active
    is_mock = settings.TTS_PROVIDER == "mock" or (
        not settings.SARVAM_API_KEY and settings.ENVIRONMENT != "production"
    )

    if is_mock and not force_mock:
        logger.info("TTS provider is mock. Prewarming is a no-op on mock TTS.")
        return {
            "total_targets": 0,
            "synthesized": 0,
            "already_cached": 0,
            "skipped_budget": 0,
            "cost_inr": 0.0,
        }

    active_tts = tts_provider or get_tts_provider()
    targets = load_prewarm_targets(messages_path, moves_dir)

    synthesized_count = 0
    cached_count = 0
    skipped_budget_count = 0
    total_cost_inr = 0.0

    logger.info("Found %d static audio targets for TTS pre-warming", len(targets))

    for label, text_hi, voice_id in targets:
        voice = get_voice(voice_id)
        cache_key = compute_cache_key(text_hi, voice.provider_speaker, voice)

        # Check idempotency via cache
        existing_audio = await tts_cache.get(cache_key, "ogg")
        if existing_audio is not None:
            cached_count += 1
            continue

        cost_est = calculate_tts_cost(text_hi)

        if dry_run:
            logger.info(
                "[DRY RUN] Would synthesize '%s' (chars=%d, est=%.4f INR)",
                label,
                len(text_hi),
                cost_est,
            )
            synthesized_count += 1
            total_cost_inr += cost_est
            continue

        # Budget verification
        can_spend = await speech_budget.can_spend(cost_est)
        if not can_spend:
            logger.warning(
                "Skipping '%s': speech budget cap reached (daily: %.2f / %.1f INR, total: %.2f / %.1f INR)",
                label,
                speech_budget.daily_spend,
                settings.SPEECH_DAILY_BUDGET_INR,
                speech_budget.total_spend,
                settings.SPEECH_TOTAL_BUDGET_INR,
            )
            skipped_budget_count += 1
            continue

        try:
            synth_res = await active_tts.synthesize(text_hi, voice=voice)
            if synth_res.audio:
                wav_bytes = (
                    synth_res.audio
                    if synth_res.fmt == "wav"
                    else await to_wav(synth_res.audio, fmt=synth_res.fmt)
                )
                await tts_cache.put_wav(cache_key, wav_bytes)
                if not is_mock:
                    await speech_budget.check_and_record_tts(text_hi)
                synthesized_count += 1
                total_cost_inr += cost_est
                logger.info("Synthesized and cached '%s' (cache_key=%s...)", label, cache_key[:12])
        except Exception as exc:
            logger.error("Failed synthesizing '%s': %s", label, exc)

    logger.info(
        "TTS Pre-warming Complete: targets=%d, synthesized=%d, already_cached=%d, skipped_budget=%d, cost=%.4f INR",
        len(targets),
        synthesized_count,
        cached_count,
        skipped_budget_count,
        total_cost_inr,
    )

    return {
        "total_targets": len(targets),
        "synthesized": synthesized_count,
        "already_cached": cached_count,
        "skipped_budget": skipped_budget_count,
        "cost_inr": total_cost_inr,
    }


def main() -> None:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(
        description="Pre-warm TTS audio cache for static messages and move learn narration."
    )
    parser.add_argument(
        "--messages-file", type=Path, default=REPO_ROOT / "content" / "messages_hi.yaml"
    )
    parser.add_argument("--moves-dir", type=Path, default=REPO_ROOT / "content" / "moves")
    parser.add_argument(
        "--force-mock", action="store_true", help="Force execution against MockTTS (for testing)"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Inspect targets without synthesizing"
    )

    args = parser.parse_args()
    res = asyncio.run(
        prewarm_tts(
            messages_path=args.messages_file,
            moves_dir=args.moves_dir,
            force_mock=args.force_mock,
            dry_run=args.dry_run,
        )
    )
    print(f"Pre-warm complete: synthesized={res['synthesized']}, cached={res['already_cached']}")


if __name__ == "__main__":
    main()
