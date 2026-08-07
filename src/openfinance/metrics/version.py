"""The metric-engine transformation version (data-model §9, ``metrics.md`` §8, §16).

Per ``docs/data-model.md`` §9, a ``TransformationVersion`` identifies the
deterministic code+config that turns raw material into derived state:

    metric_engine_version_id = hash(code_version, config_hash)

For Phase 7 the "transformation" is the **metric evaluator** that combines
canonical fact values under a formula's declarative operation tree. This module
pins that evaluator logic with a stable version id, following the exact pattern of
:class:`~openfinance.canonical.version.CanonicalFactVersion` and
:class:`~openfinance.availability.version.AvailabilityPolicy` (id is a ``sha256:``
hash of the content; nothing depends on the wall clock).

Two properties are load-bearing (``metrics.md`` Decision D5, §16; data-model §12
invariants 18, 21):

* **The pinned decimal context is part of the version.** Division can round
  (``1/3``), and the rounding depends on the :class:`decimal.Context` used. The
  context (precision + rounding mode) is folded into ``config_hash``, so a change
  to it necessarily produces a new, distinguishable ``metric_engine_version_id`` —
  a metric computed under one context can never be confused with one computed under
  another (invariant 20 analogue). The default is **precision 34,
  ``ROUND_HALF_EVEN``** (Decision D5).
* **The version depends only on code + config**, never on wall-clock time, a random
  value, or input ordering (invariant 21).

Changing the evaluator logic in a way that can alter derived metric values must
bump :data:`METRIC_ENGINE_VERSION` (or pass a new ``code_version``).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Context

from openfinance.sec.artifacts import sha256_hex

__all__ = [
    "METRIC_ENGINE_VERSION",
    "MetricEngineVersion",
    "default_decimal_context",
]

# Bump this whenever the evaluator's arithmetic/selection logic changes in a way
# that can alter derived metric values. It is the metric engine's analogue of a
# code git SHA for the (as-yet uncommitted) evaluator code. Kept explicit and
# stable so derived identity never depends on the wall clock or a random value.
METRIC_ENGINE_VERSION = "metric-engine/1"

# The pinned decimal context for all metric arithmetic (Decision D5). Precision 34
# significant digits with banker's rounding (ROUND_HALF_EVEN). Applied only via an
# explicit ``localcontext`` in the evaluator — never the ambient process context —
# so metric arithmetic is deterministic regardless of caller decimal state.
_DEFAULT_DECIMAL_PRECISION = 34
_DEFAULT_DECIMAL_ROUNDING = ROUND_HALF_EVEN


def default_decimal_context() -> Context:
    """Return a fresh copy of the pinned metric decimal context (Decision D5).

    A new instance each call so a caller can never mutate the shared context and
    perturb determinism. Precision 34, ``ROUND_HALF_EVEN``.
    """
    return Context(prec=_DEFAULT_DECIMAL_PRECISION, rounding=_DEFAULT_DECIMAL_ROUNDING)


@dataclass(frozen=True, slots=True)
class MetricEngineVersion:
    """Immutable identity of the metric-evaluator logic + config (§8).

    Attributes
    ----------
    code_version:
        Revision string for the evaluator logic (git SHA in practice).
    decimal_precision:
        Significant-digit precision of the pinned division context (Decision D5).
    decimal_rounding:
        Rounding-mode name of the pinned division context (Decision D5).
    config_hash:
        SHA-256 hex of the configuration that affects output — the decimal context
        (precision + rounding). Folding the context in makes any change to it a new
        version, since it can change a division result.
    """

    code_version: str = METRIC_ENGINE_VERSION
    decimal_precision: int = _DEFAULT_DECIMAL_PRECISION
    decimal_rounding: str = _DEFAULT_DECIMAL_ROUNDING

    @property
    def config_hash(self) -> str:
        """Deterministic ``sha256:`` hash of the decimal-context configuration."""
        payload = f"prec={self.decimal_precision}\x00round={self.decimal_rounding}"
        return f"sha256:{sha256_hex(payload.encode('utf-8'))}"

    @property
    def metric_engine_version_id(self) -> str:
        """Deterministic id: ``sha256(code_version, config_hash)`` (§9)."""
        payload = f"{self.code_version}\x00{self.config_hash}".encode()
        return f"sha256:{sha256_hex(payload)}"

    def decimal_context(self) -> Context:
        """The :class:`decimal.Context` this version pins for metric arithmetic."""
        return Context(prec=self.decimal_precision, rounding=self.decimal_rounding)
