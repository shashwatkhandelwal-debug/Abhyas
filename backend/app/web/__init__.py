"""Web application and channel API package (spec/07 §7.3, spec/09)."""

from backend.app.web.chat_api import router as chat_router

__all__ = ["chat_router"]
