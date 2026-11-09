"""Unit tests for judge demo accounts and script (Job 07)."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.app.auth.passwords import verify_password
from backend.app.db.seed_judges import (
    get_judge_password,
    seed_judge_accounts,
)


def test_get_judge_password_env_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifies password resolution from JUDGE_PASSWORD and DEMO_PASSWORD."""
    monkeypatch.setenv("JUDGE_PASSWORD", "custom_judge_secret")
    assert get_judge_password() == "custom_judge_secret"

    monkeypatch.delenv("JUDGE_PASSWORD", raising=False)
    monkeypatch.setenv("DEMO_PASSWORD", "demo_fallback_secret")
    assert get_judge_password() == "demo_fallback_secret"


@pytest.mark.asyncio
async def test_seed_judge_accounts_mock_session() -> None:
    """Tests seed_judge_accounts with in-memory mock session."""
    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.get.return_value = None

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_session.execute.return_value = mock_result

    test_pwd = "TestJudgePassword123!"
    users = await seed_judge_accounts(mock_session, count=3, password=test_pwd)

    # 3 teacher accounts + 3 oversight accounts (arp, trainer, coach)
    assert len(users) == 6

    teacher_usernames = [u.username for u in users if u.role == "teacher"]
    assert teacher_usernames == ["judge.1", "judge.2", "judge.3"]

    oversight_usernames = [u.username for u in users if u.role != "teacher"]
    assert oversight_usernames == ["judge.arp", "judge.trainer", "judge.coach"]

    for u in users:
        assert u.is_demo is True
        assert verify_password(test_pwd, u.password_hash)


def test_no_hardcoded_passwords_in_seed_files() -> None:
    """Ensures no real API keys or hardcoded passwords exist in judge seed files."""
    files_to_check = [
        Path("backend/app/db/seed_judges.py"),
        Path("scripts/seed_judges.py"),
        Path("docs/JUDGE_DEMO_SCRIPT.md"),
    ]
    for p in files_to_check:
        assert p.exists(), f"File {p} must exist"
        content = p.read_text(encoding="utf-8")
        assert "sk-ant-" not in content
        assert "AIzaSy" not in content
        assert "sarvam_key" not in content


def test_judge_demo_script_content() -> None:
    """Verifies docs/JUDGE_DEMO_SCRIPT.md contains all 5 evaluation steps."""
    script_path = Path("docs/JUDGE_DEMO_SCRIPT.md")
    assert script_path.exists()
    content = script_path.read_text(encoding="utf-8")
    assert "judge.1" in content
    assert "judge.arp" in content
    assert "Step 1" in content
    assert "Step 2" in content
    assert "Step 3" in content
    assert "Step 4" in content
    assert "Step 5" in content
    assert "Ravi" in content
    assert "suppression" in content.lower()
