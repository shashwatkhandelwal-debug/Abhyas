"""Async background worker configuration (Arq / Redis queue)."""

from typing import Any
from arq.connections import RedisSettings
from backend.app.config import settings
from backend.app.jobs.scheduler import (
    trigger_arp_weekly_digests,
    trigger_two_day_followups,
    trigger_weekly_prompts,
)


async def startup(ctx: dict[str, Any]) -> None:
    pass


async def shutdown(ctx: dict[str, Any]) -> None:
    pass


class WorkerSettings:
    functions = [
        trigger_weekly_prompts,
        trigger_two_day_followups,
        trigger_arp_weekly_digests,
    ]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(settings.REDIS_URL)
