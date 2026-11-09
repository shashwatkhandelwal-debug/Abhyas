"""Unit tests for aggregate privacy and minimum group size suppression (Job 03).

Spec & Hard Rule 7:
- Teacher practice is never shown by teacher name in oversight roles.
- Oversight roles (ARP, Trainer, Coach) see school-level aggregates only.
- Schools with fewer than N (10) practising teachers mask identifying practice details (n < 10).
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.config import settings
from backend.app.db.models import AppUser, Teacher
from backend.app.reports.arp_digest import (
    SchoolDigestRow,
    build_arp_digest,
)


@pytest.fixture
def sample_arp_user() -> AppUser:
    return AppUser(
        id=uuid.uuid4(),
        username="arp.demo",
        role="arp",
        cluster_id="KNP-C01",
        display_name="ए.आर.पी. कल्याणपुर",
        password_hash="hash",
    )


def test_aggregation_threshold_constant() -> None:
    """Settings threshold for privacy suppression must be 10."""
    assert settings.AGGREGATION_SUPPRESSION_N == 10


def test_school_digest_row_suppression_data_contract() -> None:
    """When a school has fewer than 10 teachers, suppressed=True and details are wiped."""
    row_small = SchoolDigestRow(
        school_id="प्रा.वि. छोटा",
        n_practising=3,
        suppressed=True,
        completed_loops=0,
        moves_practised=[],
        needs_help_count=0,
    )
    assert row_small.suppressed is True
    assert row_small.moves_practised == []
    assert row_small.completed_loops == 0

    row_large = SchoolDigestRow(
        school_id="प्रा.वि. बड़ा",
        n_practising=12,
        suppressed=False,
        completed_loops=8,
        moves_practised=["स्थानीय मान"],
        needs_help_count=2,
    )
    assert row_large.suppressed is False
    assert len(row_large.moves_practised) == 1
    assert row_large.completed_loops == 8


@pytest.mark.asyncio
async def test_build_arp_digest_suppresses_school_below_ten(sample_arp_user: AppUser) -> None:
    """build_arp_digest must mask school statistics if the school has fewer than 10 practising teachers."""
    mock_db = AsyncMock(spec=AsyncSession)

    cluster_mock = MagicMock()
    cluster_mock.name = "कल्याणपुर क्लस्टर 1"
    mock_db.get.return_value = cluster_mock

    # 4 teachers in School A (< 10) and 11 teachers in School B (>= 10)
    teachers_a = [
        Teacher(
            id=uuid.uuid4(),
            name=f"शिक्षिका A{i}",
            school_id="प्रा.वि. छोटा",
            cluster_id="KNP-C01",
            consent_share_scores=True,
        )
        for i in range(4)
    ]
    teachers_b = [
        Teacher(
            id=uuid.uuid4(),
            name=f"शिक्षिका B{i}",
            school_id="प्रा.वि. बड़ा",
            cluster_id="KNP-C01",
            consent_share_scores=True,
        )
        for i in range(11)
    ]
    non_consenting = [
        Teacher(
            id=uuid.uuid4(),
            name="गुप्त शिक्षिका",
            school_id="प्रा.वि. छोटा",
            cluster_id="KNP-C01",
            consent_share_scores=False,
        )
    ]

    scalars_teachers = MagicMock()
    scalars_teachers.all.return_value = teachers_a + teachers_b + non_consenting

    empty_scalars = MagicMock()
    empty_scalars.all.return_value = []
    empty_exec = MagicMock()
    empty_exec.all.return_value = []

    mock_db.scalars.side_effect = [
        scalars_teachers,
        empty_scalars,
        empty_scalars,
        empty_scalars,
    ]
    mock_db.execute.side_effect = [
        empty_exec,
    ]

    digest = await build_arp_digest(mock_db, sample_arp_user)

    assert digest.non_consenting_count == 1
    assert len(digest.school_aggregates) == 2

    # Map by school_id
    schools = {s.school_id: s for s in digest.school_aggregates}

    # School A: 4 practising consenting teachers -> suppressed
    school_a = schools["प्रा.वि. छोटा"]
    assert school_a.n_practising == 4
    assert school_a.suppressed is True
    assert school_a.moves_practised == []
    assert school_a.completed_loops == 0

    # School B: 11 practising consenting teachers -> unmasked
    school_b = schools["प्रा.वि. बड़ा"]
    assert school_b.n_practising == 11
    assert school_b.suppressed is False
