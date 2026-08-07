"""Tests for environment-driven configuration."""

from __future__ import annotations

import pytest

from quantforge.sec.config import (
    DEFAULT_MAX_REQUESTS_PER_SECOND,
    ENV_MAX_REQUESTS_PER_SECOND,
    ENV_STORAGE_DIR,
    ENV_USER_AGENT,
    SecConfig,
)
from quantforge.sec.errors import ConfigError


def test_from_env_reads_user_agent_and_storage_dir() -> None:
    cfg = SecConfig.from_env(
        {
            ENV_USER_AGENT: "QuantForge test@example.com",
            ENV_STORAGE_DIR: "/tmp/sec",
        }
    )
    assert cfg.user_agent == "QuantForge test@example.com"
    assert cfg.storage_dir == "/tmp/sec"
    assert cfg.max_requests_per_second == DEFAULT_MAX_REQUESTS_PER_SECOND


def test_missing_user_agent_is_rejected() -> None:
    with pytest.raises(ConfigError, match="User-Agent"):
        SecConfig.from_env({})


def test_user_agent_without_email_is_rejected() -> None:
    # www.sec.gov 403s without an email-format UA, so we refuse it up front.
    with pytest.raises(ConfigError, match="email-format"):
        SecConfig(user_agent="QuantForgeBot")


def test_no_personal_email_is_hardcoded() -> None:
    # Building without configuration must fail rather than silently use a
    # baked-in identity.
    with pytest.raises(ConfigError):
        SecConfig.from_env({})


def test_rate_limit_ceiling_is_enforced() -> None:
    with pytest.raises(ConfigError, match="max_requests_per_second"):
        SecConfig(user_agent="a@b.com", max_requests_per_second=25)


def test_invalid_numeric_env_is_rejected() -> None:
    with pytest.raises(ConfigError, match=ENV_MAX_REQUESTS_PER_SECOND):
        SecConfig.from_env(
            {
                ENV_USER_AGENT: "a@b.com",
                ENV_MAX_REQUESTS_PER_SECOND: "fast",
            }
        )


def test_config_is_immutable() -> None:
    cfg = SecConfig(user_agent="a@b.com")
    with pytest.raises((AttributeError, TypeError)):
        cfg.user_agent = "c@d.com"  # type: ignore[misc]
