"""QuantForge raw XBRL ingestion (Phase 3).

Parses the immutable SEC XBRL **instance** artifacts acquired by Phase 1
(:mod:`quantforge.sec`) and attributed to filings by Phase 2
(:mod:`quantforge.registry`) into an immutable, fully-provenanced,
deterministically-serialized raw-fact representation. It preserves the source
observation **exactly as reported** — facts, contexts, units, dimensions
(explicit and typed), namespaces, concepts, decimals, scale, sign, nil status,
raw lexical value — and performs **no** semantic normalization (no unit
conversion, no concept merging, no PIT selection). That is Phase 4.

Architectural chain::

    RAW SEC EVIDENCE → ACQUISITION ARTIFACTS → FILING REGISTRY → RAW XBRL FACTS
        (SEC)            (Phase 1 store)         (Phase 2)          (Phase 3)

The raw representation is *derived state*: the Phase 1 content-addressed store is
authoritative and is never overwritten, and this layer can be deleted and rebuilt
to byte-identical output from the same artifacts under the same parser version.

See ``docs/xbrl-ingestion.md`` for the full specification.
"""

from __future__ import annotations

from quantforge.xbrl.contexts import PeriodType, RawContext
from quantforge.xbrl.dimensions import (
    EMPTY_DIMENSIONS_SENTINEL,
    RawDimension,
    canonical_dimensions_key,
    dimensions_hash,
)
from quantforge.xbrl.errors import (
    MalformedXbrlError,
    UnsupportedXbrlError,
    XbrlError,
)
from quantforge.xbrl.ingest import (
    IngestResult,
    XbrlIngestor,
    source_identity_from_metadata,
)
from quantforge.xbrl.model import (
    RawDocument,
    RawFact,
    RawFactProvenance,
    raw_document_id_for_bytes,
    raw_fact_id,
)
from quantforge.xbrl.parser import (
    ParsedInstance,
    SourceIdentity,
    parse_instance,
)
from quantforge.xbrl.qnames import NamespaceContext, QName
from quantforge.xbrl.store import RAW_XBRL_FORMAT_VERSION, RawXbrlStore
from quantforge.xbrl.units import RawUnit
from quantforge.xbrl.version import XBRL_PARSER_VERSION, XbrlParserVersion

__all__ = [
    "EMPTY_DIMENSIONS_SENTINEL",
    "RAW_XBRL_FORMAT_VERSION",
    "XBRL_PARSER_VERSION",
    "IngestResult",
    "MalformedXbrlError",
    "NamespaceContext",
    "ParsedInstance",
    "PeriodType",
    "QName",
    "RawContext",
    "RawDimension",
    "RawDocument",
    "RawFact",
    "RawFactProvenance",
    "RawUnit",
    "RawXbrlStore",
    "SourceIdentity",
    "UnsupportedXbrlError",
    "XbrlError",
    "XbrlIngestor",
    "XbrlParserVersion",
    "canonical_dimensions_key",
    "dimensions_hash",
    "parse_instance",
    "raw_document_id_for_bytes",
    "raw_fact_id",
    "source_identity_from_metadata",
]
