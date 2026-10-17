from backend.app.web.arp import router as arp_router
from backend.app.web.chat_api import router as chat_router
from backend.app.web.teacher import STATIC_DIR
from backend.app.web.teacher import router as teacher_router

__all__ = ["arp_router", "chat_router", "teacher_router", "STATIC_DIR"]
