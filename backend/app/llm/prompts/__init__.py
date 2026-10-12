"""Versioned prompt templates loader (spec/05 §5.1)."""

from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parent


def load_prompt(role: str, version: str = "v1") -> str:
    """Loads a prompt markdown template by role and version."""
    path = PROMPTS_DIR / f"{role}.{version}.md"
    if not path.exists():
        raise FileNotFoundError(f"Prompt template not found: {path}")
    return path.read_text(encoding="utf-8")


__all__ = ["load_prompt"]
