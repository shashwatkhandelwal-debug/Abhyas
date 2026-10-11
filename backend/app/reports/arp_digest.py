"""ARP weekly digest generator (§13).

Strict privacy enforcement: Only includes individual teacher names/scores
if consent_share_scores == True.
"""

from typing import Any

from pydantic import BaseModel


class ARPDigestItem(BaseModel):
    teacher_name: str
    practised_move: str
    rehearsal_completed: bool
    struggled_on: list[str] = []
    asked_questions: list[str] = []


class ARPDigestSummary(BaseModel):
    cluster_id: str
    total_teachers: int
    active_teachers_count: int
    unanswered_questions_count: int
    consenting_teacher_details: list[ARPDigestItem]
    suggested_visits: list[str]


def generate_arp_digest(
    cluster_id: str,
    teachers_data: list[dict[str, Any]],
) -> ARPDigestSummary:
    """Generates the weekly digest sent to the cluster ARP."""
    active_count = 0
    consenting_items: list[ARPDigestItem] = []
    suggested_visits: list[str] = []

    for t in teachers_data:
        if t.get("practised_this_week"):
            active_count += 1

        # Strict privacy check
        if t.get("consent_share_scores"):
            item = ARPDigestItem(
                teacher_name=t["name"],
                practised_move=t.get("move_id", "N/A"),
                rehearsal_completed=t.get("rehearsal_completed", False),
                struggled_on=t.get("struggled_on", []),
                asked_questions=t.get("questions", []),
            )
            consenting_items.append(item)
            if t.get("needs_visit_support"):
                suggested_visits.append(t["name"])

    return ARPDigestSummary(
        cluster_id=cluster_id,
        total_teachers=len(teachers_data),
        active_teachers_count=active_count,
        unanswered_questions_count=sum(len(t.get("questions", [])) for t in teachers_data),
        consenting_teacher_details=consenting_items,
        suggested_visits=suggested_visits,
    )
