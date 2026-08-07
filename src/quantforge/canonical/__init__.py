"""QuantForge canonical financial observation layer (Phase 4).

Transforms the immutable, loss-preserving :class:`~quantforge.xbrl.model.RawFact`
records produced by Phase 3 into deterministic, structured canonical
:class:`~quantforge.canonical.model.Fact` records — one canonical observation per
``(obs_key, filing, transformation version)`` — while retaining **complete
lineage** back to every raw fact, raw document, source artifact, and SEC filing.

Architectural chain::

    RAW SEC EVIDENCE → ACQUISITION → FILING REGISTRY → RAW XBRL → CANONICAL FACT
        (SEC)          (Phase 1)       (Phase 2)        (Phase 3)     (Phase 4)

The canonical representation is *derived state*: the Phase 1 content-addressed
store is authoritative, the Phase 3 raw store is its faithful parse, and this
layer can be deleted and rebuilt to byte-identical output from the same raw
records under the same normalizer version.

What Phase 4 does: concept/taxonomy classification (no aggressive mapping),
period canonicalization (no fiscal inference), conservative unit canonicalization
(UNKNOWN when unsure), safe scale/sign folding into an exact-``Decimal`` base-unit
value (nil ≠ zero), deterministic ``obs_key``/``fact_id``, and complete
provenance. What it does **not** do (deferred to Phase 5+): point-in-time
selection, public-availability derivation, restatement resolution, factors,
backtesting.

See ``docs/canonicalization.md`` for the full specification.
"""

from __future__ import annotations

from quantforge.canonical.canonicalize import Canonicalizer, CanonicalizeResult
from quantforge.canonical.concept import Concept, concept_from_clark
from quantforge.canonical.errors import (
    CanonicalContradictionError,
    CanonicalError,
)
from quantforge.canonical.ingest import (
    CanonicalizationIngestor,
    CanonicalizeIngestResult,
)
from quantforge.canonical.model import (
    CanonicalDimension,
    Fact,
    FactProvenance,
    fact_id,
    obs_key,
)
from quantforge.canonical.numeric import (
    NumericValue,
    canonical_decimal_str,
    canonicalize_numeric,
)
from quantforge.canonical.period import CanonicalPeriod, canonicalize_period
from quantforge.canonical.store import (
    CANONICAL_FACTS_FORMAT_VERSION,
    CanonicalFactStore,
)
from quantforge.canonical.taxonomy import Taxonomy, classify_taxonomy
from quantforge.canonical.units import (
    CANONICAL_UNIT_UNKNOWN,
    CanonicalUnit,
    canonicalize_unit,
)
from quantforge.canonical.version import (
    CANONICAL_FACT_VERSION,
    CanonicalFactVersion,
)

__all__ = [
    "CANONICAL_FACTS_FORMAT_VERSION",
    "CANONICAL_FACT_VERSION",
    "CANONICAL_UNIT_UNKNOWN",
    "CanonicalContradictionError",
    "CanonicalDimension",
    "CanonicalError",
    "CanonicalFactStore",
    "CanonicalFactVersion",
    "CanonicalPeriod",
    "CanonicalUnit",
    "CanonicalizationIngestor",
    "CanonicalizeIngestResult",
    "CanonicalizeResult",
    "Canonicalizer",
    "Concept",
    "Fact",
    "FactProvenance",
    "NumericValue",
    "Taxonomy",
    "canonical_decimal_str",
    "canonicalize_numeric",
    "canonicalize_period",
    "canonicalize_unit",
    "classify_taxonomy",
    "concept_from_clark",
    "fact_id",
    "obs_key",
]
