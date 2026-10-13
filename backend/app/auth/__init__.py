"""Authentication and role-based access module (spec/09 §9.7, spec/03 §3.3)."""

from backend.app.auth.access import (
    apply_aggregation_suppression,
    can_access_teacher,
    can_view_teacher_scores,
    get_teacher_display_name_for_arp,
    scope_teachers_query,
)
from backend.app.auth.guards import (
    get_current_user,
    get_current_user_optional,
    require_role,
)
from backend.app.auth.router import router

__all__ = [
    "router",
    "get_current_user",
    "get_current_user_optional",
    "require_role",
    "can_access_teacher",
    "can_view_teacher_scores",
    "get_teacher_display_name_for_arp",
    "scope_teachers_query",
    "apply_aggregation_suppression",
]
