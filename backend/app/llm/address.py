"""How a simulated child addresses the teacher: दीदी for her, सर for him, no word when unknown.

`fix_address` is a text-only last check on an outgoing child line (after the guards): it
collapses combined forms ("दीदी, सर", "दीदी/सर") and swaps a wrong-gender word for the right one,
or removes it when the form is unknown. It never touches numbers.
"""

from __future__ import annotations

import re

_LETTER = r"[\wऀ-ॣ०-ॿ]"
_WORDS = r"(?:दीदी|मैडम|मैम|मेम|सर)"
_SEP = r"(?:\s*(?:[,/&]|और|या)\s*|\s+)"
_RUN = re.compile(rf"(?<!{_LETTER}){_WORDS}(?:{_SEP}{_WORDS})*(?!{_LETTER})")


def address_word(address_form: str | None) -> str:
    """"दीदी" for "f", "सर" for "m", and "" (no address word) for anything else."""
    return {"f": "दीदी", "m": "सर"}.get(address_form or "", "")


def address_rule(address_form: str | None) -> str:
    """The sentence the child_voice prompt states about addressing the teacher."""
    word = address_word(address_form)
    if not word:
        return (
            "Do NOT use any address word for the teacher (no दीदी, no सर, no मैडम, no madam): "
            "just speak."
        )
    other = "सर" if word == "दीदी" else "दीदी"
    return (
        f'Address the teacher only as "{word}", at most once. Never use "{other}", never both '
        "forms together, never मैडम or मैम."
    )


def fix_address(line: str, address_form: str | None) -> str:
    """The line with every teacher address word set to the one right form (or none)."""
    word = address_word(address_form)
    out = _RUN.sub(word, line)
    if out == line:
        return line
    if not word:
        out = re.sub(r"\s+([,।?!…])", r"\1", out)
        out = re.sub(r"([,।?!…])\s*,+", r"\1", out)
        out = re.sub(r"^[\s,]+", "", out)
        out = re.sub(r"[ \t]{2,}", " ", out).strip()
        out = re.sub(r",\s*$", "", out)
    return out


__all__ = ["address_rule", "address_word", "fix_address"]
