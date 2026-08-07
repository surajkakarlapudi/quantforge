"""QuantForge Filing Registry (Phase 2).

Transforms the immutable SEC acquisition artifacts produced by Phase 1
(:mod:`quantforge.sec`) into a structured, deterministic registry of filings
and their provenance. The registry knows *about* filings — accession, form,
dates, primary document, amendment status, which raw artifacts correspond — but
never interprets the financial content inside them (that is Phase 3).

Architectural chain::

    RAW SEC EVIDENCE → ACQUISITION ARTIFACTS → FILING REGISTRY → [XBRL, Phase 3]

The registry is *derived state*: raw artifacts are authoritative and are never
overwritten, and the registry can be deleted and rebuilt to byte-identical
logical records from the same artifacts under the same transformation version.

See ``docs/filing-registry.md`` for the full specification.
"""

from __future__ import annotations

from quantforge.registry.errors import (
    AccessionFormatError,
    DocumentAssociationError,
    RegistryError,
    SourceValidationError,
)
from quantforge.registry.identity import (
    canonical_accession,
    company_id,
    filing_id,
)
from quantforge.registry.model import (
    AmendmentLinkConfidence,
    DocumentReference,
    FilingProvenance,
    FilingRecord,
    base_form,
    is_amendment_form,
)
from quantforge.registry.registry import FilingRegistry
from quantforge.registry.store import REGISTRY_FORMAT_VERSION, RegistryStore
from quantforge.registry.submissions import SubmissionsArtifact
from quantforge.registry.version import (
    REGISTRY_LOGIC_VERSION,
    TransformationVersion,
)

__all__ = [
    "REGISTRY_FORMAT_VERSION",
    "REGISTRY_LOGIC_VERSION",
    "AccessionFormatError",
    "AmendmentLinkConfidence",
    "DocumentAssociationError",
    "DocumentReference",
    "FilingProvenance",
    "FilingRecord",
    "FilingRegistry",
    "RegistryError",
    "RegistryStore",
    "SourceValidationError",
    "SubmissionsArtifact",
    "TransformationVersion",
    "base_form",
    "canonical_accession",
    "company_id",
    "filing_id",
    "is_amendment_form",
]
