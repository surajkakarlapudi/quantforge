"""The calibration-significance transformation version (Phase 29, §13).

Per data-model §9 a ``TransformationVersion`` identifies the deterministic code+config
that turns inputs into derived state:

    calibration_significance_engine_version_id = hash(code_version, config_hash)

For Phase 29 the "transformation" is the **calibration-significance engine** that turns
a declarative
:class:`~quantforge.calsig.spec.CalibrationSignificanceSpecification` (naming exactly
one sealed :class:`~quantforge.calibration.result.RiskForecastCalibration`) into a
sealed :class:`~quantforge.calsig.result.CalibrationSignificance` - the one-sample
large-sample two-sided test of whether the source's mean variance ratio differs
significantly from the null mean ``1`` (perfect calibration). This module pins that
engine logic with a stable version id, following the exact pattern of
:class:`~quantforge.mintrl.version.MinimumTrackRecordLengthEngineVersion` (the id is a
``sha256:`` of the content; nothing depends on the wall clock).

Three properties are load-bearing (data-model invariants 19-21):

* **The pinned decimal context is part of the version.** All significance arithmetic -
  the ``standard_error = dispersion / sqrt(K)`` (one ``Decimal.sqrt``), the
  ``t_statistic = (mean - 1) / standard_error``, and the two-sided
  ``p = 2·(1 - Φ(|t|))`` - runs under an explicit :class:`decimal.Context` (precision
  + rounding). It is folded into ``config_hash``, so a change to it necessarily
  produces a new, distinguishable ``calibration_significance_engine_version_id``. The
  default is **precision 34, ``ROUND_HALF_EVEN``** - identical to every prior derived
  layer.
* **The method + normal versions are part of the version.** Phase 29 computes its own
  self-contained one-sample test method (:data:`CALSIG_METHOD_VERSION`) atop the
  *reused* deterministic exact-``Decimal`` standard-normal primitive
  (:data:`CALSIG_NORMAL_VERSION`: the ``Φ`` CDF of :mod:`quantforge._stats.normal`,
  shared with Phases 23/24). Both are folded into ``config_hash``, so a change to
  *either* yields a new, distinguishable engine id.
* **The version depends only on code + config**, never on wall-clock time, a random
  value, or input ordering (invariant 21).

Changing the significance logic in a way that can alter a computed value must bump
:data:`CALSIG_ENGINE_VERSION` (the code version), :data:`CALSIG_METHOD_VERSION` (the
statistical method), or :data:`CALSIG_NORMAL_VERSION` (the normal primitive).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Context

from quantforge.sec.artifacts import sha256_hex

__all__ = [
    "CALSIG_ENGINE_VERSION",
    "CALSIG_METHOD_VERSION",
    "CALSIG_NORMAL_VERSION",
    "CALSIG_SPEC_VERSION",
    "CalibrationSignificanceEngineVersion",
    "default_decimal_context",
]

# The specification-schema version, folded into ``calibration_significance_id`` (§13).
# Bump it when the serialized meaning of a request changes - never when engine logic
# changes (that is ``CALSIG_ENGINE_VERSION``). Shares the ``calsig/1`` string with the
# identity domain tag by construction (the prior-phase precedent).
CALSIG_SPEC_VERSION = "calsig/1"

# Bump whenever the significance engine's orchestration logic changes in a way that can
# alter a computed value. The analogue of a code git SHA for the (as-yet uncommitted)
# engine; explicit and stable so derived identity never depends on the wall clock or a
# random value.
CALSIG_ENGINE_VERSION = "calsig-engine/1"

# Bump whenever Phase 29's *statistical method* changes - the one-sample test statistic
# ``t = (mean - 1) / (dispersion / sqrt(K))``, the two-sided large-sample p-value
# ``2·(1 - Φ(|t|))``, the zero-dispersion guard, or the source-status gating. Folded
# into ``config_hash`` alongside the normal-primitive version, so a method change is a
# new, distinguishable engine version (§13).
CALSIG_METHOD_VERSION = "calsig-method/1"

# Bump whenever the *reused* deterministic exact-``Decimal`` standard-normal primitive
# changes - here only the ``Φ`` CDF of :mod:`quantforge._stats.normal` (Phase 29 uses no
# ``Z⁻¹``). Folded into ``config_hash`` so a change to how the p-value's ``Φ`` is
# computed is a new, distinguishable engine version. Phase 29 reuses that primitive
# verbatim; this version string pins *which* primitive was used, never a copy of it.
CALSIG_NORMAL_VERSION = "calsig-normal/1"

# The pinned decimal context for all significance arithmetic. Precision 34 with banker's
# rounding - identical to every prior derived layer. Applied only via an explicit
# ``localcontext``, never the ambient process context, so results are deterministic
# regardless of caller decimal state.
_DEFAULT_DECIMAL_PRECISION = 34
_DEFAULT_DECIMAL_ROUNDING = ROUND_HALF_EVEN


def default_decimal_context() -> Context:
    """Return a fresh copy of the pinned calibration-significance decimal context.

    A new instance each call so a caller can never mutate the shared context and perturb
    determinism. Precision 34, ``ROUND_HALF_EVEN``.
    """
    return Context(prec=_DEFAULT_DECIMAL_PRECISION, rounding=_DEFAULT_DECIMAL_ROUNDING)


@dataclass(frozen=True, slots=True)
class CalibrationSignificanceEngineVersion:
    """Immutable identity of the significance-engine logic + config (§13).

    Attributes
    ----------
    code_version:
        Revision string for the engine logic (git SHA in practice).
    method_version:
        Revision string for Phase 29's own statistical method (the one-sample test
        statistic, the two-sided p-value, the guards); folded into ``config_hash`` so a
        method change is a new version.
    normal_version:
        Revision string for the reused deterministic exact-``Decimal`` standard-normal
        primitive (the ``Φ`` CDF); folded into ``config_hash`` so a change to how the
        p-value's ``Φ`` is computed is a new version.
    decimal_precision / decimal_rounding:
        The pinned decimal context folded into ``config_hash`` (every computed value can
        round), so any change to it is a new version.
    """

    code_version: str = CALSIG_ENGINE_VERSION
    method_version: str = CALSIG_METHOD_VERSION
    normal_version: str = CALSIG_NORMAL_VERSION
    decimal_precision: int = _DEFAULT_DECIMAL_PRECISION
    decimal_rounding: str = _DEFAULT_DECIMAL_ROUNDING

    @property
    def config_hash(self) -> str:
        """Deterministic ``sha256:`` of the decimal-context + method + normal."""
        payload = (
            f"prec={self.decimal_precision}\x00round={self.decimal_rounding}"
            f"\x00method={self.method_version}"
            f"\x00normal={self.normal_version}"
        )
        return f"sha256:{sha256_hex(payload.encode('utf-8'))}"

    @property
    def calibration_significance_engine_version_id(self) -> str:
        """Deterministic id: ``sha256(code_version, config_hash)`` (§9)."""
        payload = f"{self.code_version}\x00{self.config_hash}".encode()
        return f"sha256:{sha256_hex(payload)}"

    def decimal_context(self) -> Context:
        """The :class:`decimal.Context` this version pins for significance math."""
        return Context(prec=self.decimal_precision, rounding=self.decimal_rounding)
