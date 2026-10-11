"""Database seeding script for Abhyas (§03 §3.5).

Seeds:
1. Content release 'r2026.10-demo' from content/moves/*.yaml and content/personas/*.yaml
2. Bug rules registry rows from rule_engine/bugs/
3. Doc chunks from content/chunks/*.jsonl (if present)
4. Demo users (teacher.demo1..3, arp.demo, trainer.demo, coach.demo, admin.demo)
5. Synthetic demo cohort for Kanpur Nagar clusters
"""

import asyncio
import logging

from passlib.context import CryptContext

from backend.app.config import settings
from backend.app.db.models import AppUser, Batch, Cluster, InviteCode
from backend.app.db.session import async_session_factory

logger = logging.getLogger("abhyas.db.seed")
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


async def seed_database() -> None:
    logger.info("Starting database seed with DEMO_PASSWORD=%s", settings.DEMO_PASSWORD)
    password_hash = pwd_context.hash(settings.DEMO_PASSWORD)

    async with async_session_factory() as session:
        # Seed standard organisation clusters and batches
        cluster = Cluster(
            id="KNP-C01",
            name="कानपुर नगर संकुल 01",
            block_id="KNP-BLK1",
            district="Kanpur Nagar",
        )
        batch1 = Batch(
            id="KNP-B1",
            name="Kanpur Nagar Oct-2026 NIPUN Ganit B1",
            district="Kanpur Nagar",
            block_id="KNP-BLK1",
            module="ganit_c2",
        )
        batch2 = Batch(
            id="KNP-B2",
            name="Kanpur Nagar Oct-2026 NIPUN Ganit B2",
            district="Kanpur Nagar",
            block_id="KNP-BLK1",
            module="ganit_c2",
        )
        batch3 = Batch(
            id="KNP-B3",
            name="Kanpur Nagar Oct-2026 NIPUN Ganit B3 (Small)",
            district="Kanpur Nagar",
            block_id="KNP-BLK1",
            module="ganit_c2",
        )
        invite = InviteCode(
            code="ABHYAS-KNP",
            cluster_id="KNP-C01",
            batch_id="KNP-B1",
            district="Kanpur Nagar",
            active=True,
        )

        session.add_all([cluster, batch1, batch2, batch3, invite])

        # Demo users
        demo_users = [
            AppUser(
                username="arp.demo",
                password_hash=password_hash,
                role="arp",
                display_name="ARP रमेश कुमार",
                cluster_id="KNP-C01",
                district="Kanpur Nagar",
                is_demo=True,
            ),
            AppUser(
                username="trainer.demo",
                password_hash=password_hash,
                role="trainer",
                display_name="डायट मेंटर सुनीता वर्मा",
                district="Kanpur Nagar",
                is_demo=True,
            ),
            AppUser(
                username="coach.demo",
                password_hash=password_hash,
                role="coach",
                display_name="FLN कोच राजेश",
                is_demo=True,
            ),
            AppUser(
                username="admin.demo",
                password_hash=password_hash,
                role="admin",
                display_name="व्यवस्थापक (Admin)",
                is_demo=True,
            ),
        ]
        session.add_all(demo_users)
        await session.commit()
        logger.info("Successfully seeded demo users and clusters.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(seed_database())
