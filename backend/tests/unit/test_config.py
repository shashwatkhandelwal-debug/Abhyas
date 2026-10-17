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
            LLM_PROVIDER="anthropic",
            ANTHROPIC_API_KEY="",  # missing!
            SARVAM_API_KEY="valid-sarvam-key",
            SESSION_SECRET="a" * 64,
            PHONE_HASH_SALT="b" * 32,
            PHONE_ENC_KEY="valid-fernet-key",
            DEMO_PASSWORD="rotated-prod-password-9988",
            ADMIN_PASSWORD="rotated-admin-password-9988",
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
            ADMIN_PASSWORD="rotated-admin-password-9988",
        )
    assert "DEMO_PASSWORD" in str(exc_info.value)


def test_production_mode_defaults_fail_fast_naming_admin_password_and_phone_enc_key() -> None:
    """Settings(ENVIRONMENT='production') with defaults raises ValidationError naming ADMIN_PASSWORD and PHONE_ENC_KEY."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(ENVIRONMENT="production")
    err_str = str(exc_info.value)
    assert "ADMIN_PASSWORD" in err_str
    assert "PHONE_ENC_KEY" in err_str


def test_production_mode_default_admin_password_fails_fast() -> None:
    """Production mode must reject default dev admin password."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            ENVIRONMENT="production",
            ANTHROPIC_API_KEY="valid-anthropic-key",
            SARVAM_API_KEY="valid-sarvam-key",
            SESSION_SECRET="a" * 64,
            PHONE_HASH_SALT="b" * 32,
            PHONE_ENC_KEY="valid-fernet-key",
            DEMO_PASSWORD="rotated-prod-password-9988",
            ADMIN_PASSWORD="abhyas-admin-2026",  # forbidden dev default!
        )
    assert "ADMIN_PASSWORD" in str(exc_info.value)


def test_production_mode_default_phone_enc_key_fails_fast() -> None:
    """Production mode must reject default dev phone encryption key."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            ENVIRONMENT="production",
            ANTHROPIC_API_KEY="valid-anthropic-key",
            SARVAM_API_KEY="valid-sarvam-key",
            SESSION_SECRET="a" * 64,
            PHONE_HASH_SALT="b" * 32,
            PHONE_ENC_KEY="P5sUu77tT3i8_R1m2tZ_7lqf4xL6D-0K0A5vG4J-7-8=",  # forbidden dev default!
            DEMO_PASSWORD="rotated-prod-password-9988",
            ADMIN_PASSWORD="rotated-admin-password-9988",
        )
    assert "PHONE_ENC_KEY" in str(exc_info.value)


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
        ADMIN_PASSWORD="rotated-admin-password-9988",
    )
    assert cfg.ENVIRONMENT == "production"
    assert cfg.ANTHROPIC_API_KEY == "valid-anthropic-key"
    assert cfg.ADMIN_PASSWORD == "rotated-admin-password-9988"
