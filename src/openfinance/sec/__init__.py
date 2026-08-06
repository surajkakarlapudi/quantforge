"""SEC acquisition layer.

Phase 1 scope: safely *retrieve and preserve* SEC EDGAR source material. This
package covers HTTP transport, request throttling and retry, content-addressed
immutable storage, and acquisition metadata. It does **not** parse, normalize,
or interpret any SEC content — that belongs to later phases.

The public entry point is :func:`build_client`, which wires the layers together
from environment-driven :class:`~openfinance.sec.config.SecConfig`. Individual
layers are exported for advanced use and testing (dependency injection).
"""

from __future__ import annotations

from openfinance.sec.artifacts import (
    AcquisitionMetadata,
    Artifact,
    ArtifactType,
    sha256_hex,
)
from openfinance.sec.client import SecClient, SubmissionsPage
from openfinance.sec.config import SecConfig
from openfinance.sec.errors import (
    ArtifactConflictError,
    ConfigError,
    HttpStatusError,
    SecAcquisitionError,
    StorageError,
    TransportError,
)
from openfinance.sec.retry import RetryingHttpClient
from openfinance.sec.storage import ArtifactStore, StoreResult
from openfinance.sec.throttle import RateLimiter
from openfinance.sec.transport import (
    HttpRequest,
    HttpResponse,
    HttpTransport,
    UrllibTransport,
)

__all__ = [
    "AcquisitionMetadata",
    "Artifact",
    "ArtifactConflictError",
    "ArtifactStore",
    "ArtifactType",
    "ConfigError",
    "HttpRequest",
    "HttpResponse",
    "HttpStatusError",
    "HttpTransport",
    "RateLimiter",
    "RetryingHttpClient",
    "SecAcquisitionError",
    "SecClient",
    "SecConfig",
    "StorageError",
    "StoreResult",
    "SubmissionsPage",
    "TransportError",
    "UrllibTransport",
    "build_client",
    "sha256_hex",
]


def build_client(
    config: SecConfig | None = None,
    *,
    transport: HttpTransport | None = None,
) -> SecClient:
    """Construct a fully wired :class:`SecClient` from configuration.

    Parameters
    ----------
    config:
        Configuration to use. Defaults to :meth:`SecConfig.from_env`.
    transport:
        HTTP transport to use. Defaults to :class:`UrllibTransport`
        (standard-library, no dependencies). Injectable for tests.
    """
    cfg = config if config is not None else SecConfig.from_env()
    http_transport = transport if transport is not None else UrllibTransport()
    rate_limiter = RateLimiter(cfg.max_requests_per_second)
    retrying = RetryingHttpClient(
        http_transport, rate_limiter, max_retries=cfg.max_retries
    )
    store = ArtifactStore(cfg.storage_dir)
    return SecClient(cfg, retrying, store)
