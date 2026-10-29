"""Context for the cluster meeting pack on the ARP and trainer pages and its printable agenda.

The pack is on when `CLUSTER_PACK_ENABLED` is set or in demo mode (`v2_enabled`). Everything shown
comes from `reports.cluster_pack` (counts and stored content only), so both pages share it.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from backend.app.auth.access import SUPPRESSION_MESSAGE
from backend.app.config import settings, v2_enabled
from backend.app.core.messages import get_message
from backend.app.reports.cluster_pack import ClusterPack

IST = ZoneInfo("Asia/Kolkata")


def pack_enabled() -> bool:
    return v2_enabled(settings.CLUSTER_PACK_ENABLED)


def card_context(pack: ClusterPack | None, print_url: str) -> dict[str, Any]:
    """Keys the `_cluster_pack.html` card needs (the card is skipped when `pack` is None)."""
    return {
        "pack": pack,
        "pack_print_url": print_url,
        "suppression_n": settings.AGGREGATION_SUPPRESSION_N,
        "suppression_message": SUPPRESSION_MESSAGE,
    }


def print_context(pack: ClusterPack, scope_key: str) -> dict[str, Any]:
    """Keys the printable one-screen agenda needs."""
    items = pack.items
    return {
        "pack": pack,
        "get_message": get_message,
        "suppression_n": settings.AGGREGATION_SUPPRESSION_N,
        "suppression_message": SUPPRESSION_MESSAGE,
        "scope_text": get_message(scope_key),
        "today": datetime.now(IST).strftime("%d-%m-%Y"),
        "minutes": settings.CLUSTER_PACK_AGENDA_MINUTES,
        "item_labels": "; ".join(
            f"{i.label} ({get_message('ui_pack_teachers', n=i.teachers)})" for i in items
        ),
        "practice": pack.practice_item,
        "read_item": items[0] if items else None,
    }
