"""The last step before bot text leaves the app: no em dashes or en dashes as separators.

Runs after the guards, on the final text only, and only where a message is built (not where it is
delivered). A dash used as a separator becomes a comma. Left alone: text inside « » (the teacher's
own words, quoted verbatim), a dash between digits (a range such as 1–3), the minus sign U+2212, the
hyphen in a syllable pattern ("मे - ला"), and every citation line (the web UI removes those lines
by exact match).
"""

from __future__ import annotations

import re
import unicodedata

from backend.app.core.types import OutboundMessage

_DASHES = "—–"
_QUOTED = re.compile(r"(«[^»]*»)")
_RANGE_EN = re.compile(r"(?<=\d)–(?=\d)")
_LINE_START = re.compile(rf"(?m)^[ \t]*[{_DASHES}][ \t]*")
_SEPARATOR = re.compile(rf"[ \t]*[{_DASHES}][ \t]*")
_RANGE_MARK = "\u0000"


def _fix_piece(piece: str, *, at_line_start: bool) -> str:
    if not any(d in piece for d in _DASHES):
        return piece
    piece = _RANGE_EN.sub(_RANGE_MARK, piece)
    if at_line_start:
        piece = _LINE_START.sub("", piece)
    piece = _SEPARATOR.sub(", ", piece)
    piece = re.sub(r"([,.:;!?।]),[ \t]", r"\1 ", piece)  # a comma after punctuation adds nothing
    piece = re.sub(r",[ \t]*(?=\n|$)", "", piece)  # nothing follows: no dangling comma
    return piece.replace(_RANGE_MARK, "–")


def clean_text(text: str, protected_lines: tuple[str, ...] = ()) -> str:
    """`text` with separator dashes replaced; `protected_lines` (citation lines) are kept as is."""
    if not text or not any(d in text for d in _DASHES):
        return text
    out: list[str] = []
    for line in text.split("\n"):
        if any(p and p in line for p in protected_lines):
            out.append(line)
            continue
        pieces = _QUOTED.split(line)
        out.append(
            "".join(
                p if _QUOTED.fullmatch(p) else _fix_piece(p, at_line_start=k == 0)
                for k, p in enumerate(pieces)
            )
        )
    return unicodedata.normalize("NFC", "\n".join(out))


def normalize_outbound(msgs: list[OutboundMessage]) -> list[OutboundMessage]:
    """In place and idempotent: the text and button titles of every message."""
    for m in msgs:
        if m.text_hi:
            m.text_hi = clean_text(m.text_hi, tuple(c.line_hi for c in m.citations))
        for b in m.buttons:
            b.title_hi = clean_text(b.title_hi)
    return msgs


__all__ = ["clean_text", "normalize_outbound"]
