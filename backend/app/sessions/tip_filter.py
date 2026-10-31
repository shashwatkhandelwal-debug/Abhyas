"""fix3 K4: which handbook passages and tips may be shown with a move, and to whom.

A passage qualifies when it is about the move (key words of the move title in its summary), is not
about the home or parents or an overview of other topics, and, for a male teacher, the tip's wording has no feminine verb form addressed to
him. Nothing qualifying means no tip: nothing is invented or edited (quote text is never touched).
"""

from __future__ import annotations

import re
import unicodedata

from backend.app.config import settings
from backend.app.content_models import MoveCard

_TOKEN = re.compile("[\\w\u0900-\u097f]+")


def _norm(text: str) -> str:
    return unicodedata.normalize("NFC", text or "").casefold()


def topic_stems(move: MoveCard) -> set[str]:
    """Key-word stems of the move title: short words whole, longer ones minus their last 2 letters."""
    words = [w for w in _TOKEN.findall(_norm(move.title_hi)) if w not in settings.TIP_STOPWORDS and len(w) >= 3]
    return {w if len(w) <= 5 else w[:-2] for w in words}


def is_on_topic(move: MoveCard, *passage: str) -> bool:
    """True when the passage has at least `TIP_MIN_TOPIC_HITS` of the move's key words, and is not an
    overview of other topics (markers that the move title itself does not use)."""
    text = _norm(" ".join(passage))
    title = _norm(move.title_hi)
    hits = sum(1 for stem in topic_stems(move) if stem in text)
    if hits < settings.TIP_MIN_TOPIC_HITS:
        return False
    return not any(
        _norm(m) in text and _norm(m) not in title for m in settings.TIP_OTHER_TOPIC_MARKERS
    )


def is_home_passage(*passage: str) -> bool:
    """True for passages about doing things at home or with parents (not a classroom move)."""
    text = _norm(" ".join(passage))
    return any(_norm(m) in text for m in settings.TIP_HOME_MARKERS)


def _feminine_reader_form() -> re.Pattern[str]:
    stems = "|".join(re.escape(_norm(s)) for s in settings.TIP_FEMININE_VERB_STEMS)
    aux = "|".join(re.escape(_norm(s)) for s in settings.TIP_FEMININE_AUX)
    return re.compile(rf"(?:{stems})\s+(?:{aux})")


def has_feminine_reader_verb(text: str) -> bool:
    return _feminine_reader_form().search(_norm(text)) is not None


def chunk_qualifies(move: MoveCard, *passage: str) -> bool:
    return is_on_topic(move, *passage) and not is_home_passage(*passage)


def tip_text_qualifies(text: str, address_form: str) -> bool:
    """The tip's own wording: not about the home, and no feminine verb to a male teacher."""
    if is_home_passage(text):
        return False
    return not (address_form == "m" and has_feminine_reader_verb(text))
