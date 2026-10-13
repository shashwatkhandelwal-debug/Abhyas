"""Channels package (spec/07)."""

from backend.app.channels.base import Channel
from backend.app.channels.web import (
    WebChannel,
    get_teacher_lock,
    is_teacher_pending,
    mark_teacher_pending,
    process_inbound_web,
    reset_web_channel_state,
    set_conversation_service_factory,
    unmark_teacher_pending,
)

__all__ = [
    "Channel",
    "WebChannel",
    "get_teacher_lock",
    "is_teacher_pending",
    "mark_teacher_pending",
    "unmark_teacher_pending",
    "reset_web_channel_state",
    "set_conversation_service_factory",
    "process_inbound_web",
]
