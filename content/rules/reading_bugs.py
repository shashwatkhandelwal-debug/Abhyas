"""Reading procedural error rules (§5.2, §10)."""

from typing import Any


def bug_matra_drop(word: str) -> dict[str, Any]:
    """Drops vowel signs (matras)."""
    matras = set("ािीुूेैोौंः")
    cleaned = "".join(ch for ch in word if ch not in matras)
    return {
        "rule_id": "MATRA_DROP",
        "answer": cleaned,
        "tokens": [word, cleaned],
        "explanation": f"Bina matra ke: {cleaned}",
    }
