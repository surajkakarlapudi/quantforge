"""OpenFinance public-availability & point-in-time layer (Phase 5).

Builds the fourth PA.1 state — *"available to a hypothetical researcher"* — over
the immutable Phase 4 canonical facts, and the point-in-time (PIT) / revised query
semantics that state exists to serve. It answers the model's two knowledge-state
questions without ever letting one masquerade as the other (data-model §KS).

Architectural chain::

    SEC EVIDENCE → ACQUISITION → REGISTRY → RAW XBRL → CANONICAL → AVAILABILITY/PIT
       (SEC)        (Phase 1)    (Phase 2)  (Phase 3)  (Phase 4)      (Phase 5)

What Phase 5 does:

* **Derives** each filing's availability triple ``(derived_public_availability_
  timestamp, availability_status, availability_policy_id)`` from immutable evidence
  (acceptance/filing/report dates + the Phase 1 ``retrieved_at`` upper bound) via a
  **versioned, form-scoped, era-bounded** :class:`AvailabilityPolicy` and a pure,
  deterministic ``derive`` — fail-closed to ``unknown`` when evidence is
  insufficient (§PA, invariants 6-17).
* **Stores** the triple in a *sidecar* keyed by ``filing_id``, so a policy change
  never rewrites the content-addressed canonical facts (Decision 3).
* **Resolves** PIT and REVISED values with **distinct result types**
  (:class:`PitValue` vs :class:`RevisedValue`) and **no default mode**, so a
  historical PIT path can never accidentally consume revised history (§KS,
  invariants 27-30).
* **Pins** answers to a reproducible :class:`DatasetVersion` (Merkle manifest over
  facts + normalizer + policy set, §9).

What it does **not** do (deferred): factor computation, backtesting, a
dissemination-index fetch (so status is ``derived``/``unknown`` only, never
``verified`` — Decision 4), and any network I/O.

See ``docs/point-in-time.md`` for the full specification.
"""

from __future__ import annotations

from openfinance.availability.calendar import (
    is_us_business_day,
    next_us_business_day,
)
from openfinance.availability.errors import (
    AvailabilityConsistencyError,
    AvailabilityError,
    ModeError,
    PolicyConfigurationError,
)
from openfinance.availability.ingest import (
    AvailabilityIngestor,
    CompanyAvailabilityResult,
)
from openfinance.availability.model import (
    AvailabilityStatus,
    FilingAvailability,
    FilingEvidence,
)
from openfinance.availability.policy import derive, select_policy
from openfinance.availability.resolve import (
    EligibleObservation,
    PitValue,
    PointInTimeResolver,
    RevisedValue,
)
from openfinance.availability.store import (
    AVAILABILITY_FORMAT_VERSION,
    AvailabilityStore,
)
from openfinance.availability.version import (
    AvailabilityPolicy,
    AvailabilityRule,
    DatasetVersion,
    PolicyConfidence,
    PolicyStatus,
    edgar_std_v1,
    merkle_root,
)

__all__ = [
    "AVAILABILITY_FORMAT_VERSION",
    "AvailabilityConsistencyError",
    "AvailabilityError",
    "AvailabilityIngestor",
    "AvailabilityPolicy",
    "AvailabilityRule",
    "AvailabilityStatus",
    "AvailabilityStore",
    "CompanyAvailabilityResult",
    "DatasetVersion",
    "EligibleObservation",
    "FilingAvailability",
    "FilingEvidence",
    "ModeError",
    "PitValue",
    "PointInTimeResolver",
    "PolicyConfidence",
    "PolicyConfigurationError",
    "PolicyStatus",
    "RevisedValue",
    "derive",
    "edgar_std_v1",
    "is_us_business_day",
    "merkle_root",
    "next_us_business_day",
    "select_policy",
]
