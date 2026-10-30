"""Plain records of one stored rehearsal (leaf module: imported by the repository and My progress)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class TurnView:
    """One of her tagged turns, as stored (the words are only used to skip stop commands)."""

    transcript: str
    acts: tuple[str, ...]
    addressed_child: str | None = None


@dataclass(frozen=True)
class Rehearsal:
    move_id: str
    when: datetime
    one_on_one: bool
    turns: tuple[TurnView, ...]


__all__ = ["Rehearsal", "TurnView"]
