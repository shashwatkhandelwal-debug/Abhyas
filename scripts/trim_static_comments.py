"""Trims redundant comments from static CSS and JS assets to maintain <150KB budget."""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = ROOT / "backend" / "app" / "web" / "static"


def trim_app_css() -> int:
    path = STATIC_DIR / "app.css"
    content = path.read_text(encoding="utf-8")
    before = len(content.encode("utf-8"))
    cleaned = re.sub(r"/\*.*?\*/", "", content, flags=re.DOTALL)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = unicodedata.normalize("NFC", cleaned)
    path.write_text(cleaned, encoding="utf-8")
    after = len(cleaned.encode("utf-8"))
    return before - after


def trim_chat_js() -> int:
    path = STATIC_DIR / "chat.js"
    content = path.read_text(encoding="utf-8")
    before = len(content.encode("utf-8"))
    # Replace top docstring with a single concise line
    cleaned = re.sub(r"/\*\*.*?\*/", "// Abhyas Chat Client (spec/09)", content, flags=re.DOTALL)
    cleaned = re.sub(r"// ──.*?──+\n?", "", cleaned)
    cleaned = re.sub(r"/\* capture is best-effort \*/", "", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = unicodedata.normalize("NFC", cleaned)
    path.write_text(cleaned, encoding="utf-8")
    after = len(cleaned.encode("utf-8"))
    return before - after


def trim_recorder_js() -> int:
    path = STATIC_DIR / "recorder.js"
    content = path.read_text(encoding="utf-8")
    before = len(content.encode("utf-8"))
    cleaned = re.sub(r"/\*\*.*?\*/", "// Abhyas Voice Recorder (spec/06)", content, flags=re.DOTALL)
    cleaned = re.sub(r"//.*?$", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = unicodedata.normalize("NFC", cleaned)
    path.write_text(cleaned, encoding="utf-8")
    after = len(cleaned.encode("utf-8"))
    return before - after


def trim_sw_js() -> int:
    path = STATIC_DIR / "sw.js"
    content = path.read_text(encoding="utf-8")
    before = len(content.encode("utf-8"))
    cleaned = re.sub(r"//.*?$", "", content, flags=re.MULTILINE)
    cleaned = re.sub(r"/\*.*?\*/", "", cleaned, flags=re.DOTALL)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = unicodedata.normalize("NFC", cleaned)
    path.write_text(cleaned, encoding="utf-8")
    after = len(cleaned.encode("utf-8"))
    return before - after


def main() -> None:
    css_saved = trim_app_css()
    chat_saved = trim_chat_js()
    rec_saved = trim_recorder_js()
    sw_saved = trim_sw_js()
    print(f"Saved {css_saved} B (app.css)")
    print(f"Saved {chat_saved} B (chat.js)")
    print(f"Saved {rec_saved} B (recorder.js)")
    print(f"Saved {sw_saved} B (sw.js)")
    print(f"Total saved: {css_saved + chat_saved + rec_saved + sw_saved} bytes")


if __name__ == "__main__":
    main()
