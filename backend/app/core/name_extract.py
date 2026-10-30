"""The name at the onboarding name step: "मेरा नाम रिया है।" must give "रिया", not the sentence.

Deterministic, no LLM. Understands the usual Hindi, romanised Hindi and English frames, strips
trailing punctuation and honorific words (जी, मैडम, मैम, दीदी, सर ...), keeps at most
`NAME_MAX_TOKENS` name words, and refuses anything that is not plainly a name (a long sentence,
digits, markup), so the caller asks again instead of storing it.
"""

from __future__ import annotations

import re
import unicodedata

from backend.app.config import settings

_TRAILING = " \t\r\n.,!?;:।॥\"'‘’“”…-"
_ALLOWED_PUNCT = frozenset(".'-’")
_HONORIFICS = frozenset(
    {"जी", "मैडम", "मैम", "मेम", "दीदी", "सर", "ji", "madam", "mam", "maam", "ma'am", "sir", "didi"}
)
# Yes/no and filler replies are never names; a leading one ("हाँ, मेरा नाम रिया है") is dropped.
_FILLERS = frozenset(
    {
        "हाँ", "हां", "हा", "जी", "नहीं", "नही", "ना", "ठीक", "है", "अच्छा", "हम्म",
        "ok", "okay", "yes", "no", "yeah", "yep", "nope", "hmm", "hm", "haan", "han", "ji",
        "nahi", "nahin", "na", "theek", "thik", "hai", "achha", "accha", "sure", "fine",
    }
)
_HU = r"हू[ँं]|हु"  # हूँ, हूं, हु

# Frames, tried in this order; group 1 is the name. Hindi and romanised Hindi are lower-cased
# by the caller, so the Latin patterns are written in lower case.
_FRAMES = tuple(
    re.compile(p)
    for p in (
        r"^मेरा\s+(?:पूरा\s+)?नाम\s+है\s+(.+)$",
        r"^(?:मेरा\s+)?नाम\s+है\s+(.+)$",
        r"^मेरा\s+(?:पूरा\s+)?नाम\s+(.+?)\s+है$",
        r"^नाम\s+(.+?)\s+है$",
        r"^(.+?)\s+है\s+मेरा\s+(?:पूरा\s+)?नाम$",
        r"^मेरा\s+(?:पूरा\s+)?नाम\s+(.+)$",
        rf"^मैं\s+(.+?)\s+(?:{_HU})$",
        r"^मुझे\s+(.+?)\s+(?:कहते|कहती|बुलाते|बुलाती)\s+(?:हैं|है|हूँ|हूं)$",
        r"^नाम[:\s]+(.+)$",
        r"^mera\s+(?:poora\s+)?naam\s+(.+?)\s+hai$",
        r"^mera\s+(?:poora\s+)?naam\s+(.+)$",
        r"^main\s+(.+?)\s+(?:hoon|hun|hu)$",
        r"^my\s+(?:full\s+)?name\s+is\s+(.+)$",
        r"^my\s+(?:full\s+)?name's\s+(.+)$",
        r"^(?:the\s+)?name\s+is\s+(.+)$",
        r"^i\s+am\s+(.+)$",
        r"^i'm\s+(.+)$",
        r"^im\s+(.+)$",
        r"^call\s+me\s+(.+)$",
        r"^this\s+is\s+(.+)$",
        r"^(?:it's|its)\s+(.+)$",
    )
)


def _clean(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text).strip(_TRAILING).split()).strip(_TRAILING)


def _drop_leading_fillers(text: str) -> str:
    """Remove yes/no words at the start; "हाँ, मेरा नाम रिया है" -> "मेरा नाम रिया है"."""
    words = text.split()
    while words and words[0].strip(_TRAILING).lower() in _FILLERS:
        words.pop(0)
    return " ".join(words)


def _is_name_word(word: str) -> bool:
    """Letters and combining marks (matras) of any script, plus . ' - inside the word."""
    if not any(unicodedata.category(c).startswith("L") for c in word):
        return False
    return all(
        unicodedata.category(c)[0] in ("L", "M") or c in _ALLOWED_PUNCT for c in word
    )


def extract_name(text: str | None, lang: str = "hi") -> str | None:
    """The teacher's name from her reply, or None when it should be asked again.

    `lang` is the UI language; the frames of both languages are always understood because
    teachers mix them, so it does not change the result.
    """
    if not text:
        return None
    cleaned = _clean(_drop_leading_fillers(_clean(text)))
    if not cleaned or any(c.isdigit() for c in cleaned):
        return None
    lowered = cleaned.lower()
    candidate: str | None = None
    framed = False
    for frame in _FRAMES:
        found = frame.match(lowered)
        if found:
            # take the original-case slice so Latin names keep their capitals
            candidate = cleaned[found.start(1) : found.end(1)]
            framed = True
            break
    if candidate is None:
        candidate = cleaned
    words = [w.strip(_TRAILING) for w in candidate.split()]
    words = [w for w in words if w and w.lower() not in _HONORIFICS]
    if words and all(w.lower() in _FILLERS for w in words):
        return None
    if not words:
        return None
    if len(words) > settings.NAME_MAX_UNFRAMED_WORDS:
        return None
    if not framed and len(cleaned.split()) > settings.NAME_MAX_UNFRAMED_WORDS:
        return None
    if not all(_is_name_word(w) for w in words):
        return None
    if len(words) > settings.NAME_MAX_TOKENS:  # first and last name
        words = [words[0], words[-1]]
    name = " ".join(words)
    return name[: settings.NAME_MAX_CHARS] or None


__all__ = ["extract_name"]
