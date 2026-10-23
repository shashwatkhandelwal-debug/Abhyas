"""Evaluates "My class": the keyword matcher, the real classifier role, and the product path.

Usage: python -m eval.class_profile_eval [--live] [--max-usd 1.0] [--out eval/class_profile/REPORT.md]

Reads eval/class_profile/sentences.yaml (32 labelled sentences). Always runs the deterministic
keyword matcher. With --live (needs ANTHROPIC_API_KEY, never printed) it also runs the real
`class_struggle_classifier` (Haiku) on every sentence and the product path (`resolve_struggles`:
classifier first, keyword matcher if it fails). Spend is metered from the API usage and the run
stops before `--max-usd`. The labels are the build team's own, not teachers'.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections import defaultdict
from collections.abc import Awaitable, Callable
from pathlib import Path

import yaml

from backend.app.class_profile.flow import resolve_struggles
from backend.app.class_profile.library import load_library
from backend.app.class_profile.matcher import match_struggles
from backend.app.config import settings
from backend.app.llm import client as llm_client
from backend.app.llm.roles.class_struggle_classifier import classify_class_struggles

ROOT = Path(__file__).resolve().parent.parent
SENTENCES = ROOT / "eval" / "class_profile" / "sentences.yaml"

Predict = Callable[[str], Awaitable[list[str] | None]]


def _score(items: list[dict[str, object]], preds: dict[str, list[str] | None]) -> dict[str, object]:
    exact = top1 = same_set = rejected = nones = fp_ids = 0
    wrong: list[str] = []
    for it in items:
        expect = list(it["expect"])  # type: ignore[call-overload]
        got = preds.get(str(it["id"])) or []
        if not expect:
            nones += 1
            if not got:
                rejected += 1
            else:
                fp_ids += len(got)
        if got == expect:
            exact += 1
        if (got[:1] == expect[:1]) or (not got and not expect):
            top1 += 1
        if set(got) == set(expect):
            same_set += 1
        if got != expect:
            wrong.append(f"{it['id']}: expected {expect}, got {got}")
    n = len(items)
    return {
        "n": n,
        "exact_order": exact,
        "top1": top1,
        "same_set": same_set,
        "none_items": nones,
        "none_rejected": rejected,
        "ids_stored_for_none": fp_ids,
        "wrong": wrong,
    }


async def _keywords(text: str) -> list[str] | None:
    return [m.struggle_id for m in match_struggles(text)]


async def _classifier(text: str) -> list[str] | None:
    lib = load_library()
    candidates = {s.id: f"{s.label_en} ({s.label_hi})" for s in lib.struggles}
    return await classify_class_struggles(text, candidates)


async def _product(text: str) -> list[str] | None:
    return (await resolve_struggles(text)).ids


async def _run(
    items: list[dict[str, object]], predict: Predict, *, stop: Callable[[], bool] | None = None
) -> tuple[dict[str, list[str] | None], int]:
    out: dict[str, list[str] | None] = {}
    skipped = 0
    for it in items:
        if stop is not None and stop():
            skipped += 1
            continue
        out[str(it["id"])] = await predict(str(it["text"]))
    return out, skipped


def _fmt(name: str, s: dict[str, object]) -> str:
    n = int(s["n"])  # type: ignore[call-overload]
    return (
        f"| {name} | {s['top1']}/{n} | {s['same_set']}/{n} | {s['exact_order']}/{n} | "
        f"{s['none_rejected']}/{s['none_items']} | {s['ids_stored_for_none']} |"
    )


async def main(live: bool, max_usd: float, out_path: Path) -> int:
    items = yaml.safe_load(SENTENCES.read_text(encoding="utf-8"))
    lib_ids = set(load_library().ids())
    for it in items:
        assert set(it["expect"]) <= lib_ids, it["id"]  # labels must be library ids

    results: dict[str, dict[str, object]] = {}
    preds_by: dict[str, dict[str, list[str] | None]] = {}
    kw, _ = await _run(items, _keywords)
    results["keyword matcher (no model)"] = _score(items, kw)
    preds_by["keyword matcher (no model)"] = kw
    spend_usd = 0.0
    skipped = 0

    if live:
        if not settings.ANTHROPIC_API_KEY or settings.LLM_PROVIDER == "mock":
            print("ANTHROPIC_API_KEY not set (or LLM_PROVIDER=mock): live part skipped.")
            return 1
        per_model: dict[str, list[int]] = defaultdict(lambda: [0, 0])
        real_log = llm_client.log_llm_call

        async def metered(**kwargs: object) -> None:
            per_model[str(kwargs.get("model", ""))][0] += int(kwargs.get("input_tokens", 0) or 0)  # type: ignore[call-overload]
            per_model[str(kwargs.get("model", ""))][1] += int(kwargs.get("output_tokens", 0) or 0)  # type: ignore[call-overload]
            await real_log(**kwargs)  # type: ignore[arg-type]

        def usd() -> float:
            return sum(
                tin / 1e6 * settings.HAIKU_INPUT_USD_PER_MTOK
                + tout / 1e6 * settings.HAIKU_OUTPUT_USD_PER_MTOK
                for tin, tout in per_model.values()
            )

        llm_client.log_llm_call = metered  # type: ignore[assignment]
        settings.LLM_CALL_LOG_ENABLED = False
        stop = lambda: usd() > max_usd * 0.9  # noqa: E731
        llm, s1 = await _run(items, _classifier, stop=stop)
        prod, s2 = await _run(items, _product, stop=stop)
        skipped = s1 + s2
        spend_usd = usd()
        results["class_struggle_classifier (Haiku, real)"] = _score(
            [i for i in items if str(i["id"]) in llm], llm
        )
        results["product path (classifier, then keywords)"] = _score(
            [i for i in items if str(i["id"]) in prod], prod
        )
        preds_by["class_struggle_classifier (Haiku, real)"] = llm
        preds_by["product path (classifier, then keywords)"] = prod

    lines = [
        "# My class: matcher and classifier evaluation",
        "",
        f"{len(items)} sentences labelled by the build team (not by teachers), "
        "`eval/class_profile/sentences.yaml`. "
        "top-1 = the first id is the expected first id (or both empty); set = same ids in any order; "
        "exact = same ids in the same order; none-rejected = off-list sentences that stored nothing.",
        "",
        "| System | top-1 | same set | exact order | none-rejected | ids stored for off-list |",
        "|---|---|---|---|---|---|",
    ]
    lines += [_fmt(name, s) for name, s in results.items()]
    if live:
        lines += [
            "",
            f"Real-model spend: about US${spend_usd:.4f} (cap {max_usd:.2f}); skipped {skipped}.",
        ]
    for name, s in results.items():
        wrong = s["wrong"]
        lines += ["", f"## Misses: {name}", ""]
        lines += [f"- {w}" for w in wrong] if wrong else ["- none"]  # type: ignore[union-attr]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[:14]))
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--max-usd", type=float, default=1.0)
    ap.add_argument("--out", default=str(ROOT / "eval" / "class_profile" / "REPORT.md"))
    args = ap.parse_args()
    sys.exit(asyncio.run(main(args.live, args.max_usd, Path(args.out))))
