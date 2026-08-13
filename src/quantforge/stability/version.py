"""The walk-forward turnover & stability transformation version (Phase 27, §13).

Per data-model §9 a ``TransformationVersion`` identifies the deterministic code+config
that turns inputs into derived state:

    stability_engine_version_id = hash(code_version, config_hash)

For Phase 27 the "transformation" is the **walk-forward stability engine** that turns a
declarative :class:`~quantforge.stability.spec.WalkForwardStabilitySpecification`
(naming exactly one sealed
:class:`~quantforge.walkforward.result.WalkForwardEvaluation`) into a sealed
:class:`~quantforge.stability.result.WalkForwardStability` - the per-window
weight-vector stability metrics and one-way turnover plus the aggregate turnover /
concentration
profile over the walk's REALIZED windows. This module pins that engine logic with a
stable version id, following the exact pattern of
:class:`~quantforge.calibration.version.RiskForecastCalibrationEngineVersion` (the id is
a ``sha256:`` of the content; nothing depends on the wall clock).

Two properties are load-bearing (data-model invariants 19-21):

* **The pinned decimal context is part of the version.** All stability arithmetic - the
  per-window ``gross_leverage = Σ|w|``, ``concentration_hhi = Σw²``, ``effective_breadth
  = 1/HHI``, ``max_abs_weight``, the one-way ``turnover = ½Σ|Δw|``, the aggregate means,
  and the ``Decimal.sqrt`` population dispersion - runs under an explicit
  :class:`decimal.Context` (precision + rounding). It is folded into ``config_hash``, so
  a change to it necessarily produces a new, distinguishable
  ``stability_engine_version_id``. The default is **precision 34,
  ``ROUND_HALF_EVEN``** - identical to every prior derived layer.
* **The method version is part of the version.** Phase 27 computes its own
  self-contained stability statistics (:data:`STABILITY_METHOD_VERSION`). Like Phase 26
  it reuses **no** standard-normal primitive (it consumes already-sealed weights), so
  there is no ``_stats`` version to fold; ``Decimal.sqrt`` is the only transcendental.
  The method version is folded into ``config_hash``, so a change to it yields a new,
  distinguishable engine id.

Changing the stability logic in a way that can alter a computed value must bump
:data:`STABILITY_ENGINE_VERSION` (the code version) or
:data:`STABILITY_METHOD_VERSION` (the statistical method).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Context

from quantforge.sec.artifacts import sha256_hex

__all__ = [
    "STABILITY_ENGINE_VERSION",
    "STABILITY_METHOD_VERSION",
    "STABILITY_SPEC_VERSION",
    "WalkForwardStabilityEngineVersion",
    "default_decimal_context",
]

# The specification-schema version, folded into ``walk_forward_stability_id`` (§13).
# Bump it when the serialized meaning of a request changes - never when engine logic
# changes (that is ``STABILITY_ENGINE_VERSION``). Shares the ``stability/1`` string with
# the identity domain tag by construction (the prior-phase precedent).
STABILITY_SPEC_VERSION = "stability/1"

# Bump whenever the stability engine's orchestration logic changes in a way that can
# alter a computed value. The analogue of a code git SHA for the engine; explicit and
# stable so derived identity never depends on the wall clock or a random value.
STABILITY_ENGINE_VERSION = "stability-engine/1"

# Bump whenever Phase 27's *statistical method* changes - the REALIZED-window selection,
# the per-window gross leverage / concentration / effective breadth / max-abs-weight /
# one-way turnover definitions, or the aggregate mean / dispersion / min / max.
# Folded into ``config_hash`` so a method change is a new, distinguishable engine
# version (§13).
STABILITY_METHOD_VERSION = "stability-method/1"

# The pinned decimal context for all stability arithmetic. Precision 34 with banker's
# rounding - identical to every prior derived layer. Applied only via an explicit
# ``localcontext``, never the ambient process context, so results are deterministic
# regardless of caller decimal state.
_DEFAULT_DECIMAL_PRECISION = 34
_DEFAULT_DECIMAL_ROUNDING = ROUND_HALF_EVEN


def default_decimal_context() -> Context:
    """Return a fresh copy of the pinned stability decimal context.

    A new instance each call so a caller can never mutate the shared context and perturb
    determinism. Precision 34, ``ROUND_HALF_EVEN``.
    """
    return Context(prec=_DEFAULT_DECIMAL_PRECISION, rounding=_DEFAULT_DECIMAL_ROUNDING)


@dataclass(frozen=True, slots=True)
class WalkForwardStabilityEngineVersion:
    """Immutable identity of the stability-engine logic + config (§13).

    Attributes
    ----------
    code_version:
        Revision string for the engine logic (git SHA in practice).
    method_version:
        Revision string for Phase 27's own statistical method (REALIZED-window
        selection, per-window metrics, one-way turnover, aggregate mean / dispersion /
        min / max); folded into ``config_hash`` so a method change is a new version.
    decimal_precision / decimal_rounding:
        The pinned decimal context folded into ``config_hash`` (every computed value can
        round), so any change to it is a new version.
    """

    code_version: str = STABILITY_ENGINE_VERSION
    method_version: str = STABILITY_METHOD_VERSION
    decimal_precision: int = _DEFAULT_DECIMAL_PRECISION
    decimal_rounding: str = _DEFAULT_DECIMAL_ROUNDING

    @property
    def config_hash(self) -> str:
        """Deterministic ``sha256:`` hash of the decimal-context + method config."""
        payload = (
            f"prec={self.decimal_precision}\x00round={self.decimal_rounding}"
            f"\x00method={self.method_version}"
        )
        return f"sha256:{sha256_hex(payload.encode('utf-8'))}"

    @property
    def stability_engine_version_id(self) -> str:
        """Deterministic id: ``sha256(code_version, config_hash)`` (§9)."""
        payload = f"{self.code_version}\x00{self.config_hash}".encode()
        return f"sha256:{sha256_hex(payload)}"

    def decimal_context(self) -> Context:
        """The :class:`decimal.Context` this version pins for stability math."""
        return Context(prec=self.decimal_precision, rounding=self.decimal_rounding)
