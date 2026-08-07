"""Environment-driven configuration for SEC acquisition.

All tunable behaviour is captured in a single immutable :class:`SecConfig`
value object. Configuration is sourced from the environment (never from
source), and the only *required* setting is the User-Agent, because
``www.sec.gov`` returns ``403`` to requests that do not carry an
email-format User-Agent (empirically confirmed during reconnaissance).

No secrets are read or stored here. The User-Agent is contact information
that SEC's fair-access policy asks clients to disclose; it is not a
credential.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

from quantforge.sec.errors import ConfigError

__all__ = ["SecConfig"]

# Environment variable names. Kept as module constants so tests and docs can
# reference the exact spellings without duplicating string literals.
ENV_USER_AGENT: Final = "QUANTFORGE_SEC_USER_AGENT"
ENV_STORAGE_DIR: Final = "QUANTFORGE_SEC_STORAGE_DIR"
ENV_MAX_REQUESTS_PER_SECOND: Final = "QUANTFORGE_SEC_MAX_RPS"
ENV_TIMEOUT_SECONDS: Final = "QUANTFORGE_SEC_TIMEOUT"
ENV_MAX_RETRIES: Final = "QUANTFORGE_SEC_MAX_RETRIES"

# SEC asks automated clients to stay at or below 10 requests/second. We default
# below that ceiling to leave headroom for clock jitter across processes.
DEFAULT_MAX_REQUESTS_PER_SECOND: Final = 8.0
DEFAULT_TIMEOUT_SECONDS: Final = 30.0
DEFAULT_MAX_RETRIES: Final = 5
DEFAULT_STORAGE_DIR: Final = "./data/sec"


@dataclass(frozen=True, slots=True)
class SecConfig:
    """Immutable configuration for the SEC acquisition subsystem.

    Attributes
    ----------
    user_agent:
        Contact identity sent on every request. SEC requires an
        email-format value for ``www.sec.gov``. Not a secret.
    storage_dir:
        Root directory for the content-addressed artifact store. Defaults
        outside the package tree and is expected to be git-ignored.
    max_requests_per_second:
        Client-side throttle ceiling. Must be > 0 and <= 10.
    timeout_seconds:
        Per-request socket timeout.
    max_retries:
        Maximum number of *additional* attempts after the first for
        retryable failures (429/5xx/transport). ``0`` disables retries.
    """

    user_agent: str
    storage_dir: str = DEFAULT_STORAGE_DIR
    max_requests_per_second: float = DEFAULT_MAX_REQUESTS_PER_SECOND
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    max_retries: int = DEFAULT_MAX_RETRIES

    def __post_init__(self) -> None:
        if not self.user_agent or not self.user_agent.strip():
            raise ConfigError(
                "a non-empty User-Agent is required; set "
                f"{ENV_USER_AGENT} to an email-format contact string "
                "(e.g. 'QuantForge research@example.com')"
            )
        if "@" not in self.user_agent:
            raise ConfigError(
                "the SEC User-Agent must include an email-format contact; "
                f"www.sec.gov returns 403 otherwise (got {self.user_agent!r})"
            )
        if not 0 < self.max_requests_per_second <= 10:
            raise ConfigError(
                "max_requests_per_second must be in (0, 10]; got "
                f"{self.max_requests_per_second}"
            )
        if self.timeout_seconds <= 0:
            raise ConfigError(
                f"timeout_seconds must be > 0; got {self.timeout_seconds}"
            )
        if self.max_retries < 0:
            raise ConfigError(f"max_retries must be >= 0; got {self.max_retries}")

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> SecConfig:
        """Build configuration from environment variables.

        Parameters
        ----------
        environ:
            Mapping to read from. Defaults to ``os.environ``. Injectable so
            tests need not mutate global process state.
        """
        env = os.environ if environ is None else environ
        raw_user_agent = env.get(ENV_USER_AGENT, "")

        return cls(
            user_agent=raw_user_agent,
            storage_dir=env.get(ENV_STORAGE_DIR, DEFAULT_STORAGE_DIR),
            max_requests_per_second=_parse_float(
                env,
                ENV_MAX_REQUESTS_PER_SECOND,
                DEFAULT_MAX_REQUESTS_PER_SECOND,
            ),
            timeout_seconds=_parse_float(
                env, ENV_TIMEOUT_SECONDS, DEFAULT_TIMEOUT_SECONDS
            ),
            max_retries=_parse_int(env, ENV_MAX_RETRIES, DEFAULT_MAX_RETRIES),
        )


def _parse_float(env: Mapping[str, str], key: str, default: float) -> float:
    raw = env.get(key)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ConfigError(f"{key} must be a number; got {raw!r}") from exc


def _parse_int(env: Mapping[str, str], key: str, default: int) -> int:
    raw = env.get(key)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"{key} must be an integer; got {raw!r}") from exc
