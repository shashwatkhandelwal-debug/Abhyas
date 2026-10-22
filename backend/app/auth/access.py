"""Access rules and scoped query helpers enforcing data privacy (spec/03 §3.3).

Roles and permissions:
- teacher: own rows only
- arp: teachers in own cluster; scores/transcripts only if consent_share_scores is True.
       escalated questions shown as 'शिक्षक #<short hash>' if consent_share_scores is False.
- trainer: aggregate data only for own district, n < AGGREGATION_SUPPRESSION_N suppressed.
- coach: review items, drafts, anonymised transcripts.
- admin: access to all records.
- ALL: teacher_contact is never returned.
"""

from typing import Any

from backend.app.config import settings
from backend.app.core.messages import get_message
from backend.app.db.models import AppUser, Teacher


def can_access_teacher(user: AppUser, teacher: Teacher) -> bool:
    """Checks whether the user is permitted to view basic teacher metadata.

    Demo accounts (teacher.demo*, arp.demo, trainer.demo, coach.demo) can NEVER
    access non-demo teachers.
    """
    is_user_demo = getattr(user, "is_demo", False) or getattr(user, "is_demo_account", False)
    is_teacher_demo = getattr(teacher, "is_demo", False) or getattr(
        teacher, "is_demo_account", False
    )
    if is_user_demo and not is_teacher_demo:
        return False

    if user.role == "admin":
        return True
    if user.role == "teacher":
        return bool(user.teacher_id and user.teacher_id == teacher.id)
    if user.role == "arp":
        return bool(
            user.cluster_id and teacher.cluster_id and user.cluster_id == teacher.cluster_id
        )
    return False


def can_view_teacher_scores(user: AppUser, teacher: Teacher) -> bool:
    """Checks whether the user is permitted to view teacher scores and transcripts (§3.3).

    Demo accounts can NEVER view scores of non-demo teachers.
    """
    is_user_demo = getattr(user, "is_demo", False) or getattr(user, "is_demo_account", False)
    is_teacher_demo = getattr(teacher, "is_demo", False) or getattr(
        teacher, "is_demo_account", False
    )
    if is_user_demo and not is_teacher_demo:
        return False

    if user.role == "admin":
        return True
    if user.role == "teacher":
        return bool(user.teacher_id and user.teacher_id == teacher.id)
    if user.role == "arp":
        # Only in own cluster AND only if consent_share_scores is True
        if not (user.cluster_id and teacher.cluster_id and user.cluster_id == teacher.cluster_id):
            return False
        return bool(teacher.consent_share_scores)
    return False


def get_teacher_display_name_for_arp(user: AppUser, teacher: Teacher) -> str:
    """Returns real name if consenting, or anonymised code 'शिक्षक #<short hash>' if not (§3.3).

    If demo user accesses a non-demo teacher, returns empty string.
    """
    is_user_demo = getattr(user, "is_demo", False) or getattr(user, "is_demo_account", False)
    is_teacher_demo = getattr(teacher, "is_demo", False) or getattr(
        teacher, "is_demo_account", False
    )
    if is_user_demo and not is_teacher_demo:
        return ""
    if teacher.consent_share_scores and teacher.name:
        return teacher.name
    short_hash = str(teacher.id).replace("-", "")[:6]
    return get_message("ui_arp_anonymous_teacher", code=short_hash)


def scope_teachers_query(query: Any, user: AppUser) -> Any:
    """Scopes a SQLAlchemy query for Teacher to enforce role and demo boundaries.

    Demo accounts (is_demo=True) are strictly scoped to is_demo teachers.
    """
    is_user_demo = getattr(user, "is_demo", False) or getattr(user, "is_demo_account", False)
    if is_user_demo:
        query = query.where(Teacher.is_demo.is_(True))

    if user.role == "teacher":
        query = query.where(Teacher.id == user.teacher_id)
    elif user.role == "arp" and user.cluster_id:
        query = query.where(Teacher.cluster_id == user.cluster_id)
    elif user.role == "trainer" and user.district:
        query = query.where(Teacher.district == user.district)
    return query


SUPPRESSION_MESSAGE = "समूह छोटा है (n<10) — गोपनीयता हेतु छिपाया गया"


def apply_aggregation_suppression(
    row: dict[str, Any],
    n_teachers: int,
    threshold: int | None = None,
) -> dict[str, Any]:
    """Replaces sensitive metric fields with suppression notice if n < threshold (§3.3, §9.4)."""
    min_n = threshold if threshold is not None else settings.AGGREGATION_SUPPRESSION_N
    result = dict(row)
    if n_teachers < min_n:
        result["suppressed"] = True
        result["suppression_message"] = SUPPRESSION_MESSAGE
        # Mask sensitive metrics
        for metric_key in (
            "explain_missing",
            "rubric_dist",
            "ladder_dist",
            "active_rate",
            "completed_rate",
        ):
            if metric_key in result:
                result[metric_key] = SUPPRESSION_MESSAGE
    else:
        result["suppressed"] = False
    return result
