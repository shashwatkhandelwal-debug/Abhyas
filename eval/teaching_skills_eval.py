"""Evaluates "What do you want to get better at?": the real teaching_skill_classifier role.

Usage: python -m eval.teaching_skills_eval [--live] [--max-usd 1.0] [--out eval/teaching_skills/REPORT.md]

Reads eval/teaching_skills/sentences.yaml (labelled sentences). Without --live nothing is called and the
report only checks that every label is an id on the closed list. With --live (needs ANTHROPIC_API_KEY, never
printed) it runs the real `teaching_skill_classifier` (Haiku) on every sentence. A call that fails its guard
twice returns nothing (counted as no id) and the numbered list would be shown. Spend is metered from the API
usage and the run stops before `--max-usd`. The labels are the build team's own, not teachers'.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections import defaultdict
from pathlib import Path

import yaml

from backend.app.class_profile.skills import load_skills, resolve_candidates
from backend.app.config import settings
from backend.app.llm import client as llm_client
from backend.app.llm.roles.teaching_skill_classifier import classify_teaching_skills

ROOT = Path(__file__).resolve().parent.parent
SENTENCES = ROOT / "eval" / "teaching_skills" / "sentences.yaml"


def _score(items: list[dict[str, object]], preds: dict[str, list[str] | None]) -> dict[str, object]:
    exact = top1 = same_set = rejected = nones = invented = 0
    wrong: list[str] = []
    known = set(load_skills().ids())
    for it in items:
        expect = list(it["expect"])  # type: ignore[call-overload]
        got = preds.get(str(it["id"])) or []
        if not expect:
            nones += 1
            if not got:
                rejected += 1
        invented += sum(1 for g in got if g not in known)
        if got == expect:
            exact += 1
        if (got[:1] == expect[:1]) or (not got and not expect):
            top1 += 1
        if set(got) == set(expect):
            same_set += 1
        if got != expect:
            wrong.append(f"{it['id']}: expected {expect}, got {got}")
    return {
        "n": len(items),
        "exact_order": exact,
        "top1": top1,
        "same_set": same_set,
        "none_items": nones,
        "none_rejected": rejected,
        "ids_outside_list": invented,
        "wrong": wrong,
    }


async def main(live: bool, max_usd: float, out_path: Path) -> int:
    items = yaml.safe_load(SENTENCES.read_text(encoding="utf-8"))
    lib_ids = set(load_skills().ids())
    for it in items:
        assert set(it["expect"]) <= lib_ids, it["id"]  # labels must be ids on the list

    lines = [
        "# Teaching skills: classifier evaluation",
        "",
        f"{len(items)} sentences labelled by the build team (not by teachers), "
        "`eval/teaching_skills/sentences.yaml`. top-1 = the first id is the expected first id (or both "
        "empty); set = same ids in any order; exact = same ids in the same order; none-rejected = "
        "vague or off-topic sentences that stored nothing (the chips come back).",
        "",
    ]
    if not live:
        lines += ["Not run live: every label was checked against the closed list only."]
    else:
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
        candidates = resolve_candidates()
        raw: dict[str, list[str] | None] = {}
        skipped = 0
        for it in items:
            if usd() > max_usd * 0.9:
                skipped += 1
                continue
            raw[str(it["id"])] = await classify_teaching_skills(str(it["text"]), candidates)
        done = [i for i in items if str(i["id"]) in raw]
        s = _score(done, raw)
        n = int(s["n"])  # type: ignore[call-overload]
        lines += [
            "| System | top-1 | same set | exact order | none-rejected | ids outside the list |",
            "|---|---|---|---|---|---|",
            f"| teaching_skill_classifier (Haiku, real) | {s['top1']}/{n} | {s['same_set']}/{n} | "
            f"{s['exact_order']}/{n} | {s['none_rejected']}/{s['none_items']} | {s['ids_outside_list']} |",
            "",
            f"Real-model spend: about US${usd():.4f} (cap {max_usd:.2f}); skipped {skipped}. A call that "
            "fails its guard twice returns nothing (counted as no id) and the numbered list is shown.",
            "",
            "## Misses",
            "",
        ]
        lines += [f"- {w}" for w in s["wrong"]] if s["wrong"] else ["- none"]  # type: ignore[union-attr]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[:12]))
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--max-usd", type=float, default=1.0)
    ap.add_argument("--out", default=str(ROOT / "eval" / "teaching_skills" / "REPORT.md"))
    args = ap.parse_args()
    sys.exit(asyncio.run(main(args.live, args.max_usd, Path(args.out))))
