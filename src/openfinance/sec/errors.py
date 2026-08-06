"""Exception hierarchy for the SEC acquisition layer.

Every error raised by this package derives from :class:`SecAcquisitionError`,
so callers can catch the whole subsystem with a single ``except`` clause while
still discriminating between configuration, transport, HTTP, and storage
failures when they need to.
"""

from __future__ import annotations

__all__ = [
    "ArtifactConflictError",
    "ConfigError",
    "HttpStatusError",
    "SecAcquisitionError",
    "StorageError",
    "TransportError",
]


class SecAcquisitionError(Exception):
    """Base class for all errors raised by the SEC acquisition layer."""


class ConfigError(SecAcquisitionError):
    """Configuration is missing or invalid (e.g. no User-Agent supplied)."""


class TransportError(SecAcquisitionError):
    """A network-level failure (timeout, DNS, connection reset).

    Distinct from :class:`HttpStatusError`, which represents a completed HTTP
    exchange that returned an unacceptable status code.
    """


class HttpStatusError(SecAcquisitionError):
    """The server returned a non-success status that we will not retry past.

    Raised after retries are exhausted (429/5xx) or immediately for permanent
    client errors (e.g. 403, 404).
    """

    def __init__(self, status: int, url: str, *, attempts: int = 1) -> None:
        self.status = status
        self.url = url
        self.attempts = attempts
        super().__init__(f"HTTP {status} for {url} after {attempts} attempt(s)")


class StorageError(SecAcquisitionError):
    """A failure while persisting or reading a raw artifact."""


class ArtifactConflictError(StorageError):
    """An existing artifact's bytes do not match their content address.

    Content-addressed storage keys a blob by the SHA-256 of its bytes, so this
    indicates on-disk corruption: the file stored at ``<hash>`` no longer
    hashes to ``<hash>``. We fail closed rather than silently overwrite.
    """

    def __init__(self, sha256: str, actual_sha256: str) -> None:
        self.sha256 = sha256
        self.actual_sha256 = actual_sha256
        super().__init__(
            f"artifact {sha256} is corrupted: on-disk bytes hash to {actual_sha256}"
        )
