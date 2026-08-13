"""The risk-forecast-calibration transformation version (Phase 26, §13).

Per data-model §9 a ``TransformationVersion`` identifies the deterministic code+config
that turns inputs into derived state:

    risk_forecast_calibration_engine_version_id = hash(code_version, config_hash)

For Phase 26 the "transformation" is the **risk-forecast-calibration engine** that turns
a declarative
:class:`~quantforge.calibration.spec.RiskForecastCalibrationSpecification` (naming
exactly one sealed :class:`~quantforge.walkforward.result.WalkForwardEvaluation`) into a
sealed :class:`~quantforge.calibration.result.RiskForecastCalibration` - the per-window
forecast-vs-outcome ratios and the aggregate bias / dispersion statistics over the
walk's calibratable windows. This module pins that engine logic with a stable version
id, following the exact pattern of
:class:`~quantforge.multiplicity.version.MultipleComparisonEngineVersion` (the id is a
``sha256:`` of the content; nothing depends on the wall clock).

Two properties are load-bearing (data-model invariants 19-21):

* **The pinned decimal context is part of the version.** All calibration arithmetic
  - the per-window ``variance_ratio = realized / predicted``, the ``Decimal.sqrt``
  volatilities and volatility ratios, the pooled ``aggregate_bias = sum_realized /
  sum_predicted``, the mean ratio, the population dispersion, and the under-forecast
  frequency - runs under an explicit :class:`decimal.Context` (precision +
  rounding). It is folded into ``config_hash``, so a change to it necessarily
  produces a new, distinguishable ``risk_forecast_calibration_engine_version_id``.
  The default is **precision 34, ``ROUND_HALF_EVEN``** - identical to every prior
  derived layer.
* **The method version is part of the version.** Phase 26 computes its own
  self-contained calibration statistics (:data:`CALIBRATION_METHOD_VERSION`). Like
  Phase 25 it reuses **no** standard-normal primitive (it consumes already-sealed
  variances), so there is no ``_stats`` version to fold; ``Decimal.sqrt`` is the
  only transcendental. The method version is folded into ``config_hash``, so a
  change to it yields a new, distinguishable engine id.

Changing the calibration logic in a way that can alter a computed value must bump
:data:`CALIBRATION_ENGINE_VERSION` (the code version) or
:data:`CALIBRATION_METHOD_VERSION` (the statistical method).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Context

from quantforge.sec.artifacts import sha256_hex

__all__ = [
    "CALIBRATION_ENGINE_VERSION",
    "CALIBRATION_METHOD_VERSION",
    "CALIBRATION_SPEC_VERSION",
    "RiskForecastCalibrationEngineVersion",
    "default_decimal_context",
]

# The specification-schema version, folded into ``risk_forecast_calibration_id`` (§13).
# Bump it when the serialized meaning of a request changes - never when engine logic
# changes (that is ``CALIBRATION_ENGINE_VERSION``). Shares the ``calibration/1`` string
# with the identity domain tag by construction (the prior-phase precedent).
CALIBRATION_SPEC_VERSION = "calibration/1"

# Bump whenever the calibration engine's orchestration logic changes in a way that can
# alter a computed value. The analogue of a code git SHA for the (as-yet uncommitted)
# engine; explicit and stable so derived identity never depends on the wall clock or a
# random value.
CALIBRATION_ENGINE_VERSION = "calibration-engine/1"

# Bump whenever Phase 26's *statistical method* changes - the calibratable-window
# selection (REALIZED + KNOWN, positive predicted variance) and exclusion mapping,
# the per-window variance / volatility ratios, the pooled ``aggregate_bias``, the
# mean ratio, the population dispersion, the under-forecast frequency, or the min /
# max ratios. Folded into ``config_hash`` so a method change is a new,
# distinguishable engine version (§13).
CALIBRATION_METHOD_VERSION = "calibration-method/1"

# The pinned decimal context for all calibration arithmetic. Precision 34 with banker's
# rounding - identical to every prior derived layer. Applied only via an explicit
# ``localcontext``, never the ambient process context, so results are deterministic
# regardless of caller decimal state.
_DEFAULT_DECIMAL_PRECISION = 34
_DEFAULT_DECIMAL_ROUNDING = ROUND_HALF_EVEN


def default_decimal_context() -> Context:
    """Return a fresh copy of the pinned calibration decimal context.

    A new instance each call so a caller can never mutate the shared context and perturb
    determinism. Precision 34, ``ROUND_HALF_EVEN``.
    """
    return Context(prec=_DEFAULT_DECIMAL_PRECISION, rounding=_DEFAULT_DECIMAL_ROUNDING)


@dataclass(frozen=True, slots=True)
class RiskForecastCalibrationEngineVersion:
    """Immutable identity of the calibration-engine logic + config (§13).

    Attributes
    ----------
    code_version:
        Revision string for the engine logic (git SHA in practice).
    method_version:
        Revision string for Phase 26's own statistical method (calibratable-window
        selection, per-window ratios, pooled bias, mean, dispersion, under-forecast
        frequency, min / max); folded into ``config_hash`` so a method change is a new
        version.
    decimal_precision / decimal_rounding:
        The pinned decimal context folded into ``config_hash`` (every computed value can
        round), so any change to it is a new version.
    """

    code_version: str = CALIBRATION_ENGINE_VERSION
    method_version: str = CALIBRATION_METHOD_VERSION
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
    def risk_forecast_calibration_engine_version_id(self) -> str:
        """Deterministic id: ``sha256(code_version, config_hash)`` (§9)."""
        payload = f"{self.code_version}\x00{self.config_hash}".encode()
        return f"sha256:{sha256_hex(payload)}"

    def decimal_context(self) -> Context:
        """The :class:`decimal.Context` this version pins for calibration math."""
        return Context(prec=self.decimal_precision, rounding=self.decimal_rounding)
