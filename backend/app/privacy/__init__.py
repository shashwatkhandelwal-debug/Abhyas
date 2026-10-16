"""Privacy, retention, and data purge utilities (spec/03 §3.3, spec/08 §8.1)."""

from backend.app.privacy.purge import purge_teacher_data

__all__ = ["purge_teacher_data"]
