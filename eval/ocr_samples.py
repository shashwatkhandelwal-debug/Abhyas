"""Save random (page image, OCR text) pairs so a human can compare them.

python eval/ocr_samples.py [--n 10] [--seed 2026]

Writes docs/ocr_samples/<source>_p<NNN>.png and .txt plus an index. Pages are drawn at random
(fixed seed) from the pages that became chunks, split evenly across the OCR'd guides.
"""

from __future__ import annotations

import argparse
import importlib
import random
import sys
from pathlib import Path
from typing import Any

import yaml

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from backend.app.retrieval.page_ocr import (  # noqa: E402
    SOURCES_DIR,
    image_key,
    is_unreliable,
    load_cached,
    render_page,
)

OUT = REPO / "docs" / "ocr_samples"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=10)
    ap.add_argument("--seed", type=int, default=2026)
    args = ap.parse_args()

    pymupdf: Any = importlib.import_module("pymupdf")
    entries = [
        e
        for e in yaml.safe_load((SOURCES_DIR / "sources.yaml").read_text(encoding="utf-8"))
        if e.get("ocr")
    ]
    rng = random.Random(args.seed)
    OUT.mkdir(parents=True, exist_ok=True)
    index: list[str] = []
    per_source = args.n // len(entries)
    for entry in entries:
        doc = pymupdf.open(str(SOURCES_DIR / entry["file"]))
        usable: list[int] = []
        pngs: dict[int, bytes] = {}
        for n in range(1, len(doc) + 1):
            png, _w, _h = render_page(doc, n)
            cached = load_cached(entry["id"], image_key(png))
            if cached and not is_unreliable(cached) and len(cached.text_hi.split()) >= 40:
                usable.append(n)
                pngs[n] = png
        for n in sorted(rng.sample(usable, per_source)):
            stem = f"{entry['id']}_p{n:03d}"
            (OUT / f"{stem}.png").write_bytes(pngs[n])
            cached = load_cached(entry["id"], image_key(pngs[n]))
            assert cached is not None
            (OUT / f"{stem}.txt").write_text(cached.text_hi + "\n", encoding="utf-8")
            index.append(f"| `{stem}.png` | `{stem}.txt` | {entry['id']} | {n} |")
    (OUT / "README.md").write_text(
        "# OCR spot-check pairs\n\n"
        "Random pages (seed {seed}) from the two UP Hindi guides: the page image next to the text the\n"
        "`page_ocr` role read from it. Open each pair and compare; the measured error rate is in\n"
        "`content/sources/README.md`.\n\n"
        "| Image | OCR text | Source | PDF page |\n|---|---|---|---|\n{rows}\n".format(
            seed=args.seed, rows="\n".join(index)
        ),
        encoding="utf-8",
    )
    print(f"wrote {len(index)} pairs to {OUT}")


if __name__ == "__main__":
    main()
