"""What worked for other teachers (flag PEER_WORKED_ENABLED): one line, only when data allows.

After a follow-up answer of "still stuck" or "could not try", and on the check-in tip screen, one
line says how many teachers reported that the practice for this struggle worked:
"इस दिक्कत में <N> शिक्षकों ने बताया कि '<move name>' वाला तरीका काम किया।"

Counts are distinct consenting teachers (`consent_share_scores`) with a "worked" follow-up answer in
the last `PEER_WORKED_WINDOW_DAYS` days, not counting her. Scope: her cluster when at least
`AGGREGATION_SUPPRESSION_N` teachers there, else all teachers when at least that many, else the line
is left out entirely. No names, no schools, no free text; demo and real teachers are never mixed.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta

from backend.app.class_profile.library import StruggleLibrary, load_library
from backend.app.config import settings, v2_enabled
from backend.app.core.messages import get_message
from backend.app.sessions.titles import move_title

Counter = Callable[[str | None], Awaitable[int]]  # cluster id (None: everyone) to a teacher count


def enabled() -> bool:
    return v2_enabled(settings.PEER_WORKED_ENABLED)


def choose_scope(n_cluster: int | None, n_all: int, minimum: int | None = None) -> int | None:
    """The count to show: the cluster's when it reaches the minimum, else everyone's, else None."""
    floor = settings.AGGREGATION_SUPPRESSION_N if minimum is None else minimum
    if n_cluster is not None and n_cluster >= floor:
        return n_cluster
    if n_all >= floor:
        return n_all
    return None


async def peer_line(
    struggle_id: str | None,
    *,
    cluster_id: str | None,
    count: Counter,
    lib: StruggleLibrary | None = None,
) -> str | None:
    """The one line, or None. `count(cluster_id)` is awaited at most twice (cluster, then all)."""
    if not struggle_id:
        return None
    struggle = (lib or load_library()).get(struggle_id)
    if struggle is None or struggle.move_id is None:
        return None
    n_cluster = await count(cluster_id) if cluster_id else None
    n_all = 0
    if n_cluster is None or n_cluster < settings.AGGREGATION_SUPPRESSION_N:
        n_all = await count(None)
    n = choose_scope(n_cluster, n_all)
    if n is None:
        return None
    return get_message("pw_line", n=n, move=move_title(struggle.move_id))


def window_start(now: datetime) -> datetime:
    return now - timedelta(days=settings.PEER_WORKED_WINDOW_DAYS)


__all__ = ["choose_scope", "enabled", "peer_line", "window_start"]
