"""Unit tests for configuration validation and fail-fast behavior (§14 T02)."""

import pytest
from pydantic import ValidationError

from backend.app.config import Settings


def test_development_mode_loads_with_defaults() -> None:
    """In development mode, empty keys fall back to mocks without raising."""
    cfg = Settings(
        ENVIRONMENT="development",
        ANTHROPIC_API_KEY="",
        SARVAM_API_KEY="",
    )
    assert cfg.ENVIRONMENT == "development"
    assert cfg.MAX_TURNS_PER_REHEARSAL == 8
    assert cfg.COACH_CONFIDENCE_THRESHOLD == 0.60
    assert cfg.AGGREGATION_SUPPRESSION_N == 10
    assert cfg.LLM_DAILY_TOKEN_BUDGET == 3_000_000


def test_production_mode_missing_anthropic_fails_fast() -> None:
    """Production mode must raise ValueError/ValidationError if required secrets are missing."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            ENVIRONMENT="production",
            ANTHROPIC_API_KEY="",  # missing!
            SARVAM_API_KEY="valid-sarvam-key",
            SESSION_SECRET="a" * 64,
            PHONE_HASH_SALT="b" * 32,
            PHONE_ENC_KEY="valid-fernet-key",
            DEMO_PASSWORD="rotated-prod-password-9988",
        )
    assert "ANTHROPIC_API_KEY" in str(exc_info.value)


def test_production_mode_default_demo_password_fails_fast() -> None:
    """Production mode must reject default dev demo password."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            ENVIRONMENT="production",
            ANTHROPIC_API_KEY="valid-anthropic-key",
            SARVAM_API_KEY="valid-sarvam-key",
            SESSION_SECRET="a" * 64,
            PHONE_HASH_SALT="b" * 32,
            PHONE_ENC_KEY="valid-fernet-key",
            DEMO_PASSWORD="abhyas-demo-2026",  # forbidden in prod!
        )
    assert "DEMO_PASSWORD" in str(exc_info.value)


def test_production_mode_with_all_secrets_succeeds() -> None:
    """Production mode succeeds when all required secrets are provided."""
    cfg = Settings(
        ENVIRONMENT="production",
        ANTHROPIC_API_KEY="valid-anthropic-key",
        SARVAM_API_KEY="valid-sarvam-key",
        SESSION_SECRET="a" * 64,
        PHONE_HASH_SALT="b" * 32,
        PHONE_ENC_KEY="valid-fernet-key",
        DEMO_PASSWORD="rotated-prod-password-9988",
    )
    assert cfg.ENVIRONMENT == "production"
    assert cfg.ANTHROPIC_API_KEY == "valid-anthropic-key"
