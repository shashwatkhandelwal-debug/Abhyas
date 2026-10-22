"""Per-PDF extraction check: chars/page, Devanagari ratio, legacy-font garbage heuristics."""

from __future__ import annotations

import sys
import unicodedata
from pathlib import Path

import pypdf


def main(paths: list[str]) -> None:
    for p in paths:
        path = Path(p)
        if not path.exists():
            print(f"{path.name}: ABSENT")
            continue
        reader = pypdf.PdfReader(str(path))
        n = len(reader.pages)
        counts: list[int] = []
        dev = alpha = 0
        legacy = 0
        sample = ""
        for i in range(n):
            t = unicodedata.normalize("NFC", reader.pages[i].extract_text() or "")
            counts.append(len(t.strip()))
            dev += sum(1 for c in t if "ऀ" <= c <= "ॿ")
            alpha += sum(1 for c in t if c.isalpha())
            # legacy-font mojibake: Latin-1 supplement / odd symbols dominate
            legacy += sum(1 for c in t if "À" <= c <= "ÿ" or c in "¤¥§¨©ª«¬®¯°±²³")
            if not sample and len(t) > 300 and i > 5:
                sample = t[:160].replace("\n", " ")
        empty = sum(1 for c in counts if c < 30)
        print(
            f"{path.name}: pages={n} total_chars={sum(counts)} avg/page={sum(counts) // max(n, 1)} "
            f"min={min(counts)} max={max(counts)} near_empty_pages={empty} "
            f"devanagari_ratio={dev / max(alpha, 1):.2f} legacy_chars={legacy}"
        )
        print(
            "  per-page chars:",
            counts if n <= 60 else f"first30={counts[:30]} ... last10={counts[-10:]}",
        )
        print("  sample:", sample)


if __name__ == "__main__":
    main(sys.argv[1:])
