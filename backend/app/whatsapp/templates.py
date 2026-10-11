"""Pre-approved Meta Utility Template builders (§11)."""

from typing import Any


def build_weekly_move_prompt_template(
    teacher_name: str,
    move_title_hi: str,
    sankul_month: str,
) -> dict[str, Any]:
    """Utility template: Sent on Monday to initiate the weekly loop."""
    return {
        "name": "abhyas_weekly_move_prompt",
        "language": {"code": "hi"},
        "components": [
            {
                "type": "body",
                "parameters": [
                    {"type": "text", "text": teacher_name},
                    {"type": "text", "text": move_title_hi},
                    {"type": "text", "text": sankul_month},
                ],
            }
        ],
    }


def build_two_day_followup_template(
    teacher_name: str,
    question_summary: str,
) -> dict[str, Any]:
    """Utility template: Follow up 2 days after an ASK query (§8)."""
    return {
        "name": "abhyas_two_day_followup",
        "language": {"code": "hi"},
        "components": [
            {
                "type": "body",
                "parameters": [
                    {"type": "text", "text": teacher_name},
                    {"type": "text", "text": question_summary},
                ],
            }
        ],
    }


def build_arp_digest_template(
    arp_name: str,
    cluster_name: str,
    active_teachers_count: int,
    digest_url: str,
) -> dict[str, Any]:
    """Utility template: Weekly summary sent to the cluster ARP (§13)."""
    return {
        "name": "abhyas_arp_weekly_digest",
        "language": {"code": "hi"},
        "components": [
            {
                "type": "body",
                "parameters": [
                    {"type": "text", "text": arp_name},
                    {"type": "text", "text": cluster_name},
                    {"type": "text", "text": str(active_teachers_count)},
                    {"type": "text", "text": digest_url},
                ],
            }
        ],
    }
