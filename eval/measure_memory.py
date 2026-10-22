"""Resident memory of the app process: after import, with the full retrieval index, after one scene.

Usage: python -m eval.measure_memory [--no-scene]

Steps, each followed by a resident-set reading (psutil): (1) interpreter plus `backend.app.main`
imported (all routers, templates not yet rendered); (2) the guide retriever built over every
chunk file in `content/chunks/` (what the first question or the first scene builds in the app);
(3) one real one-on-one scene (four teacher turns with the real Claude models, no speech) plus
coach feedback. Prints the peak working set as well.

The figures are for the machine that runs the script (Windows resident set, Python 3.12), not for
the Render free instance (Linux, 512 MB).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import platform
import sys
import uuid

import psutil

from backend.app.config import settings


def rss_mb() -> float:
    return float(psutil.Process().memory_info().rss) / (1024 * 1024)


def peak_mb() -> float | None:
    info = psutil.Process().memory_info()
    peak = getattr(info, "peak_wset", None)
    return float(peak) / (1024 * 1024) if peak else None


async def one_scene() -> None:
    from backend.app.rehearsal.scene_runner import SceneRunner
    from backend.app.rehearsal.scene_store import InMemorySceneStore
    from eval.one_on_one_live import SCENES

    sc = SCENES[0]
    runner = SceneRunner(store=InMemorySceneStore())
    record = await runner.create_scene(uuid.uuid4(), sc.move_id, one_on_one_persona=sc.child)
    for line in sc.turns:
        await runner.turn(record.scene_id, line, synthesize_audio=False)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-scene", action="store_true")
    args = parser.parse_args()
    settings.LLM_CALL_LOG_ENABLED = False

    out: dict[str, object] = {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "rss_mb_interpreter": round(rss_mb(), 1),
    }
    import backend.app.main  # noqa: F401  (routers, templates, clients)

    out["rss_mb_after_app_import"] = round(rss_mb(), 1)

    from backend.app.retrieval.search import get_guide_retriever

    retriever = get_guide_retriever()
    out["chunks_in_index"] = len(retriever._chunks)
    out["rss_mb_after_full_index"] = round(rss_mb(), 1)

    if not args.no_scene:
        if not settings.ANTHROPIC_API_KEY or settings.LLM_PROVIDER == "mock":
            out["scene"] = "skipped: no ANTHROPIC_API_KEY"
        else:
            asyncio.run(one_scene())
            out["rss_mb_after_one_scene"] = round(rss_mb(), 1)
    out["peak_working_set_mb"] = None if peak_mb() is None else round(peak_mb() or 0.0, 1)
    sys.stdout.buffer.write((json.dumps(out, indent=2) + "\n").encode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
