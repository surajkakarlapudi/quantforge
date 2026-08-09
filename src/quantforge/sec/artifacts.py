"""Artifact types and acquisition metadata.

An *artifact* is a single immutable blob of bytes retrieved from SEC, together
with the metadata describing how and when it was obtained. This module defines:

* :class:`ArtifactType` — the closed set of SEC source materials this layer
  knows how to acquire (raw retrieval only; no parsing).
* :class:`AcquisitionMetadata` — the reproducibility record captured for every
  retrieval.
* :class:`Artifact` — bytes + metadata, the unit written to the store.

Artifact *identity* is the SHA-256 of the bytes (content addressing). Metadata
— including retrieval timestamps — is descriptive provenance and never part of
the identity, so re-fetching identical bytes yields the same artifact.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum

__all__ = [
    "AcquisitionMetadata",
    "Artifact",
    "ArtifactType",
    "sha256_hex",
]


class ArtifactType(StrEnum):
    """The closed set of SEC raw materials this layer retrieves.

    Values are stable slugs used in the storage layout and metadata. Members
    cover the submissions/companyfacts JSON APIs, the filing package index, the
    primary document, and each XBRL component (instance + linkbases). We store
    these verbatim; interpreting them belongs to later phases.
    """

    SUBMISSIONS = "submissions"
    COMPANY_FACTS = "company_facts"
    COMPANY_TICKERS = "company_tickers"
    FILING_INDEX = "filing_index"
    FILING_DOCUMENT = "filing_document"
    XBRL_INSTANCE = "xbrl_instance"
    XBRL_SCHEMA = "xbrl_schema"
    XBRL_CALCULATION = "xbrl_calculation"
    XBRL_DEFINITION = "xbrl_definition"
    XBRL_LABEL = "xbrl_label"
    XBRL_PRESENTATION = "xbrl_presentation"
    # Phase 11 market-data raw tiers. These reuse the Phase 1 content-addressed
    # ArtifactStore verbatim, so a raw vendor payload needs a valid ArtifactType
    # slug. Market bytes always carry ``accession=None`` and live in a sibling
    # ``<root>/market/raw/`` store, so they can never be associated to an SEC
    # filing (registry.documents.associate_documents skips ``accession is None``)
    # — the SEC acquisition tree is untouched.
    MARKET_DAILY_BARS = "market_daily_bars"
    MARKET_CORPORATE_ACTIONS = "market_corporate_actions"


def sha256_hex(data: bytes) -> str:
    """Return the lowercase hex SHA-256 digest of ``data``."""
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True, slots=True)
class AcquisitionMetadata:
    """Provenance for one retrieval, sufficient to reproduce and audit it.

    This record is descriptive only. None of its fields participate in artifact
    identity — that is solely the SHA-256 of the bytes — so two retrievals of
    the same bytes at different times produce two metadata records pointing at
    one immutable blob.

    Attributes
    ----------
    source_url:
        The exact URL fetched.
    artifact_type:
        Which kind of SEC material this is.
    sha256:
        Content address of the retrieved bytes.
    retrieved_at:
        ISO-8601 UTC timestamp of when the bytes were received. Provenance
        only; supplied by the caller (injected clock) for reproducibility.
    http_status:
        The status of the exchange that produced the bytes (200; a 304 reuses
        the prior blob and records the reused hash).
    content_type / content_length:
        Server-reported metadata, as received.
    etag / last_modified:
        Conditional-request validators returned by the server, retained so a
        future acquisition can issue ``If-None-Match`` / ``If-Modified-Since``.
    user_agent:
        The request identity used, captured for reproducibility. Not a secret.
    cik / accession:
        Populated when known from the request context; ``None`` otherwise.
    """

    source_url: str
    artifact_type: ArtifactType
    sha256: str
    retrieved_at: str
    http_status: int
    user_agent: str
    content_type: str | None = None
    content_length: int | None = None
    etag: str | None = None
    last_modified: str | None = None
    cik: str | None = None
    accession: str | None = None

    def to_dict(self) -> dict[str, object]:
        """Serialize to a JSON-ready dict with sorted, stable keys."""
        return {
            "source_url": self.source_url,
            "artifact_type": self.artifact_type.value,
            "sha256": self.sha256,
            "retrieved_at": self.retrieved_at,
            "http_status": self.http_status,
            "user_agent": self.user_agent,
            "content_type": self.content_type,
            "content_length": self.content_length,
            "etag": self.etag,
            "last_modified": self.last_modified,
            "cik": self.cik,
            "accession": self.accession,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, object]) -> AcquisitionMetadata:
        """Rebuild metadata from a :meth:`to_dict` record.

        Inverse of :meth:`to_dict`. Used by consumers (e.g. the filing
        registry) that read persisted provenance records back off disk. The
        record must carry the required fields written by :meth:`to_dict`; a
        missing required field or an unknown ``artifact_type`` raises.
        """
        try:
            return cls(
                source_url=_require_str(raw, "source_url"),
                artifact_type=ArtifactType(_require_str(raw, "artifact_type")),
                sha256=_require_str(raw, "sha256"),
                retrieved_at=_require_str(raw, "retrieved_at"),
                http_status=_require_int(raw, "http_status"),
                user_agent=_require_str(raw, "user_agent"),
                content_type=_optional_str(raw, "content_type"),
                content_length=_optional_int(raw, "content_length"),
                etag=_optional_str(raw, "etag"),
                last_modified=_optional_str(raw, "last_modified"),
                cik=_optional_str(raw, "cik"),
                accession=_optional_str(raw, "accession"),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"invalid acquisition metadata record: {exc}") from exc


@dataclass(frozen=True, slots=True)
class Artifact:
    """Immutable bytes plus their acquisition metadata."""

    data: bytes = field(repr=False)
    metadata: AcquisitionMetadata

    @property
    def sha256(self) -> str:
        return self.metadata.sha256


def _require_str(raw: Mapping[str, object], key: str) -> str:
    value = raw[key]
    if not isinstance(value, str):
        raise TypeError(f"{key} must be a string, got {type(value).__name__}")
    return value


def _require_int(raw: Mapping[str, object], key: str) -> int:
    value = raw[key]
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{key} must be an int, got {type(value).__name__}")
    return value


def _optional_str(raw: Mapping[str, object], key: str) -> str | None:
    value = raw.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"{key} must be a string or null")
    return value


def _optional_int(raw: Mapping[str, object], key: str) -> int | None:
    value = raw.get(key)
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{key} must be an int or null")
    return value
