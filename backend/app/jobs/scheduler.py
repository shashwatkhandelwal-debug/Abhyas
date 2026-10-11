"""Scheduled background tasks for weekly loops, reminders, and ARP digests (§1, §4, §8, §13)."""

import logging
from datetime import datetime, timezone
from backend.app.config import settings

logger = logging.getLogger(__name__)


async def trigger_weekly_prompts() -> None:
    """Dispatches Monday morning utility templates to all enrolled teachers."""
    logger.info("Executing scheduled task: trigger_weekly_prompts")


async def trigger_two_day_followups() -> None:
    """Dispatches follow-up questions for 'Ask Any Time' inquiries logged 48h prior."""
    logger.info("Executing scheduled task: trigger_two_day_followups (48h follow-up)")


async def trigger_arp_weekly_digests() -> None:
    """Compiles and sends weekly digest messages to ARPs."""
    logger.info("Executing scheduled task: trigger_arp_weekly_digests")
