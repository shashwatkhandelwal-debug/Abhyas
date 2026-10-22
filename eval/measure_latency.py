"""Per-stage latency of the real rehearsal pipeline: act_tagger, engine, child_voice, coach.

Usage: python -m eval.measure_latency [--scenes 10] [--max-usd 0.60] [--out PATH]

Drives the same code path as the app (`SceneRunner.turn`, then `coach_feedback`) with the real
Claude models through ANTHROPIC_API_KEY (never printed) and no speech (no STT/TTS call). Stage
times for the three model roles come from the `llm_role ... latency_ms=... fallback_used=...` log
lines the app already writes; the rule engine is timed around `RuleEngine.step`. Reports p50 / p95
per stage and the share of calls that used the deterministic fallback. At most `--scenes` scenes
(default and cap: 10, the scripted scenes of `eval.one_on_one_live`).

These numbers are measured on the machine that runs the script, not on the hosted service.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import math
import re
import sys
import time
import uuid
from collections import defaultdict
from pathlib import Path

from backend.app.config import settings
from backend.app.llm import client as llm_client
from backend.app.llm.roles.coach import coach_feedback
from backend.app.llm.schemas import SceneTurn
from backend.app.rehearsal.diagnosis import diagnose
from backend.app.rehearsal.scene_runner import SceneRunner, load_move_card
from backend.app.rehearsal.scene_store import InMemorySceneStore
from backend.app.rule_engine.domain import ChildState, TeachingAct
from backend.app.rule_engine.engine import RuleEngine
from eval.one_on_one_live import SCENES

MAX_SCENES = 10
STAGES = ("act_tagger", "engine", "child_voice", "coach")
ROLE_LINE = re.compile(r"llm_role role=(\w+) model=\S+ latency_ms=(\d+) fallback_used=(true|false)")


def percentile(values: list[float], q: float) -> float:
    """Nearest-rank percentile (q in 0..100); 0.0 for an empty list."""
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = max(1, math.ceil(q / 100 * len(ordered)))
    return ordered[rank - 1]


class RoleTimings(logging.Handler):
    """Collects (latency_ms, fallback_used) per role from the app's own log lines."""

    def __init__(self) -> None:
        super().__init__(logging.INFO)
        self.by_role: dict[str, list[tuple[float, bool]]] = defaultdict(list)

    def emit(self, record: logging.LogRecord) -> None:
        m = ROLE_LINE.search(record.getMessage())
        if m:
            self.by_role[m.group(1)].append((float(m.group(2)), m.group(3) == "true"))


class Spend:
    def __init__(self) -> None:
        self.tokens: dict[str, list[int]] = defaultdict(lambda: [0, 0])

    def add(self, model: str, tin: int, tout: int) -> None:
        self.tokens[model][0] += tin
        self.tokens[model][1] += tout

    def usd(self) -> float:
        total = 0.0
        for model, (tin, tout) in self.tokens.items():
            if "sonnet" in model:
                total += tin / 1e6 * settings.SONNET_INPUT_USD_PER_MTOK
                total += tout / 1e6 * settings.SONNET_OUTPUT_USD_PER_MTOK
            else:
                total += tin / 1e6 * settings.HAIKU_INPUT_USD_PER_MTOK
                total += tout / 1e6 * settings.HAIKU_OUTPUT_USD_PER_MTOK
        return total


def render(
    timings: dict[str, list[tuple[float, bool]]], n_scenes: int, n_turns: int, spend: Spend
) -> str:
    lines = [
        f"Scenes: {n_scenes}, teacher turns: {n_turns}, estimated spend: US${spend.usd():.3f}",
        "",
        "| Stage | Calls | p50 (ms) | p95 (ms) | Fallback used |",
        "|---|---|---|---|---|",
    ]
    for stage in STAGES:
        rows = timings.get(stage, [])
        ms = [r[0] for r in rows]
        fb = sum(1 for r in rows if r[1])
        share = f"{fb}/{len(rows)} ({fb / len(rows):.0%})" if rows else "-"
        lines.append(
            f"| {stage} | {len(rows)} | {percentile(ms, 50):.1f} | {percentile(ms, 95):.1f} | {share} |"
        )
    all_rows = [r for s in ("act_tagger", "child_voice", "coach") for r in timings.get(s, [])]
    fb_all = sum(1 for r in all_rows if r[1])
    lines.append("")
    lines.append(
        f"Share of model-role calls that used the fallback: {fb_all}/{len(all_rows)}"
        + (f" ({fb_all / len(all_rows):.0%})" if all_rows else "")
    )
    return "\n".join(lines)


async def run(n_scenes: int, max_usd: float) -> tuple[str, int]:
    if not settings.ANTHROPIC_API_KEY or settings.LLM_PROVIDER == "mock":
        return "ANTHROPIC_API_KEY not set (or LLM_PROVIDER=mock): nothing to measure.", 1

    spend = Spend()
    real_log = llm_client.log_llm_call

    async def metered(**kwargs: object) -> None:
        spend.add(
            str(kwargs.get("model", "")),
            int(kwargs.get("input_tokens", 0) or 0),  # type: ignore[call-overload]
            int(kwargs.get("output_tokens", 0) or 0),  # type: ignore[call-overload]
        )
        await real_log(**kwargs)  # type: ignore[arg-type]

    llm_client.log_llm_call = metered  # type: ignore[assignment]
    settings.LLM_CALL_LOG_ENABLED = False

    handler = RoleTimings()
    client_logger = logging.getLogger("abhyas.llm.client")
    client_logger.addHandler(handler)
    client_logger.setLevel(logging.INFO)

    engine_ms: list[tuple[float, bool]] = []
    real_step = RuleEngine.step

    def timed_step(*args: object, **kwargs: object) -> object:
        started = time.perf_counter()
        try:
            return real_step(*args, **kwargs)  # type: ignore[arg-type]
        finally:
            engine_ms.append(((time.perf_counter() - started) * 1000, False))

    RuleEngine.step = staticmethod(timed_step)  # type: ignore[method-assign,assignment]

    store = InMemorySceneStore()
    runner = SceneRunner(store=store)
    scenes_done = 0
    turns_done = 0
    for sc in SCENES[: min(n_scenes, MAX_SCENES)]:
        if spend.usd() > max_usd * 0.92:
            break
        move = load_move_card(sc.move_id)
        record = await runner.create_scene(uuid.uuid4(), sc.move_id, one_on_one_persona=sc.child)
        true_mid = record.scene_state.children[0].misconception
        diag = await diagnose(sc.diagnosis, move, true_mid)
        for teacher_line in sc.turns:
            result = await runner.turn(record.scene_id, teacher_line, synthesize_audio=False)
            turns_done += 1
            if result.turn.ended:
                break
        final = await store.get(record.scene_id)
        assert final is not None
        spoken: list[SceneTurn] = []
        acts: list[list[TeachingAct]] = []
        for t in final.turns:
            spoken.append(SceneTurn(speaker="teacher", text_hi=t.transcript))
            acts.append([TeachingAct(a) for a in t.acts if a in TeachingAct._value2member_map_])
            for cl in t.child_lines:
                if cl.line_hi:
                    spoken.append(SceneTurn(speaker=cl.persona_id, text_hi=cl.line_hi))
        child = final.scene_state.children[0]
        trajectory = [ChildState.MISCONCEPTION, *[h[1] for h in child.history]]
        await coach_feedback(
            move=move.one_on_one_view(),
            turns=spoken,
            acts=acts,
            trajectories={sc.child: trajectory},
            target_child_id=sc.child,
            current_item_answer=final.scene_state.current_item.answer(),
            diagnosis=diag,
            one_on_one=True,
        )
        scenes_done += 1

    timings = dict(handler.by_role)
    timings["engine"] = engine_ms
    return render(timings, scenes_done, turns_done, spend), 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenes", type=int, default=MAX_SCENES)
    parser.add_argument("--max-usd", type=float, default=0.60)
    parser.add_argument("--out", default="")
    args = parser.parse_args()
    report, code = asyncio.run(run(args.scenes, args.max_usd))
    sys.stdout.buffer.write((report + "\n").encode("utf-8"))
    if code == 0 and args.out:
        Path(args.out).write_text(report + "\n", encoding="utf-8")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
