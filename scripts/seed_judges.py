"""CLI script to seed per-judge demo accounts (spec/09 §9.7, Job 07).

Usage:
    python scripts/seed_judges.py [--count 5]

Passwords are read from the JUDGE_PASSWORD or DEMO_PASSWORD env vars.
Never commits credentials.
"""

import argparse
import asyncio
import logging
import sys

from backend.app.db.seed_judges import seed_judge_accounts
from backend.app.db.session import async_session_factory

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("abhyas.scripts.seed_judges")


async def main() -> int:
    parser = argparse.ArgumentParser(description="Seed dedicated demo accounts for hackathon judges.")
    parser.add_argument(
        "--count",
        type=int,
        default=5,
        help="Number of per-judge teacher accounts to seed (default: 5).",
    )
    args = parser.parse_args()

    logger.info("Connecting to database to seed %d judge accounts...", args.count)
    try:
        async with async_session_factory() as session:
            async with session.begin():
                users = await seed_judge_accounts(session, count=args.count)
        logger.info("Successfully seeded %d judge accounts. No credentials logged.", len(users))
        return 0
    except Exception as e:
        logger.error("Failed to seed judge accounts: %s", e)
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
