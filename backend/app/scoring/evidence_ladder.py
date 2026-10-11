"""Evidence Ladder for Classroom Adoption (§7)."""

from enum import IntEnum
from typing import Any

from pydantic import BaseModel


class AdoptionLevel(IntEnum):
    REHEARSED = 1  # Completed simulation rehearsal
    SELF_REPORTED = 2  # Teacher filled guided reflection
    PEER_OBSERVED = 3  # Colleague completed 5-min checklist
    ARP_OBSERVED = 4  # ARP logged verified observation on school visit
    CHILDREN_IMPROVED = 5  # Measured classroom learning gains


class EvidenceRecord(BaseModel):
    teacher_id: str
    move_id: str
    level: AdoptionLevel
    source: str
    detail: dict[str, Any] = {}
    label_en: str
    label_hi: str


def get_adoption_level_metadata(level: AdoptionLevel) -> tuple[str, str]:
    labels = {
        AdoptionLevel.REHEARSED: ("Rehearsed with AI children", "अभ्यास पूरा किया"),
        AdoptionLevel.SELF_REPORTED: ("Self-reported reflection", "कक्षा अनुभव साझा किया"),
        AdoptionLevel.PEER_OBSERVED: (
            "Peer observed (5-min checklist)",
            "सहकर्मी शिक्षक द्वारा देखा गया",
        ),
        AdoptionLevel.ARP_OBSERVED: ("ARP observed on visit", "एआरपी द्वारा निरीक्षण किया गया"),
        AdoptionLevel.CHILDREN_IMPROVED: ("Measured child improvement", "बच्चों के परिणाम में सुधार"),
    }
    return labels[level]
