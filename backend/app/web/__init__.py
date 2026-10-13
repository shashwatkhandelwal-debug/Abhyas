"""Web application and channel API package (spec/07 §7.3, spec/09)."""

from backend.app.web.chat_api import router as chat_router
from backend.app.web.teacher import STATIC_DIR
from backend.app.web.teacher import router as teacher_router

__all__ = ["chat_router", "teacher_router", "STATIC_DIR"]
