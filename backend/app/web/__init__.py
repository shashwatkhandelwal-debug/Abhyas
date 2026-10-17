"""Web application and channel API package (spec/07 §7.3, spec/09)."""

from backend.app.web.admin import router as admin_router
from backend.app.web.arp import router as arp_router
from backend.app.web.chat_api import router as chat_router
from backend.app.web.review import router as review_router
from backend.app.web.teacher import STATIC_DIR
from backend.app.web.teacher import router as teacher_router
from backend.app.web.trainer import router as trainer_router

__all__ = [
    "admin_router",
    "arp_router",
    "chat_router",
    "review_router",
    "teacher_router",
    "trainer_router",
    "STATIC_DIR",
]
