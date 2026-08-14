"""The net-of-cost-significance transformation version (Phase 32, §13).

Per data-model §9 a ``TransformationVersion`` identifies the deterministic code+config
that turns inputs into derived state:

    net_of_cost_significance_engine_version_id = hash(code_version, config_hash)

For Phase 32 the "transformation" is the **net-of-cost-significance engine** that turns
a declarative
:class:`~quantforge.netcostsig.spec.NetOfCostSignificanceSpecification` (naming exactly
one sealed :class:`~quantforge.netcost.result.NetOfCostPerformance`) into a sealed
:class:`~quantforge.netcostsig.result.NetOfCostSignificance` - the one-sample
large-sample **upper-tailed** test of whether the source's after-cost mean return is
significantly greater than the null mean ``0`` (no after-cost edge). This module pins
that engine logic with a stable version id, following the exact pattern of
:class:`~quantforge.calsig.version.CalibrationSignificanceEngineVersion` (the id is a
``sha256:`` of the content; nothing depends on the wall clock).

Three properties are load-bearing (data-model invariants 19-21):

* **The pinned decimal context is part of the version.** All significance arithmetic -
  the ``standard_error = net_volatility / sqrt(n)`` (one ``Decimal.sqrt``), the
  ``t_statistic = (net_mean - 0) / standard_error``, and the one-sided
  ``p = 1 - Φ(t)`` - runs under an explicit :class:`decimal.Context` (precision +
  rounding). It is folded into ``config_hash``, so a change to it necessarily produces a
  new, distinguishable ``net_of_cost_significance_engine_version_id``. The default is
  **precision 34, ``ROUND_HALF_EVEN``** - identical to every prior derived layer.
* **The method + normal versions are part of the version.** Phase 32 computes its own
  self-contained one-sample test method (:data:`NETCOSTSIG_METHOD_VERSION`) atop the
  *reused* deterministic exact-``Decimal`` standard-normal primitive
  (:data:`NETCOSTSIG_NORMAL_VERSION`: the ``Φ`` CDF of :mod:`quantforge._stats.normal`,
  shared with Phases 23/24/29). Both are folded into ``config_hash``, so a change to
  *either* yields a new, distinguishable engine id.
* **The version depends only on code + config**, never on wall-clock time, a random
  value, or input ordering (invariant 21).

Changing the significance logic in a way that can alter a computed value must bump
:data:`NETCOSTSIG_ENGINE_VERSION` (the code version), :data:`NETCOSTSIG_METHOD_VERSION`
(the statistical method), or :data:`NETCOSTSIG_NORMAL_VERSION` (the normal primitive).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Context

from quantforge.sec.artifacts import sha256_hex

__all__ = [
    "NETCOSTSIG_ENGINE_VERSION",
    "NETCOSTSIG_METHOD_VERSION",
    "NETCOSTSIG_NORMAL_VERSION",
    "NETCOSTSIG_SPEC_VERSION",
    "NetOfCostSignificanceEngineVersion",
    "default_decimal_context",
]

# The specification-schema version, folded into ``net_of_cost_significance_id`` (§13).
# Bump it when the serialized meaning of a request changes - never when engine logic
# changes (that is ``NETCOSTSIG_ENGINE_VERSION``). Shares the ``netcostsig/1`` string
# with the identity domain tag by construction (the prior-phase precedent).
NETCOSTSIG_SPEC_VERSION = "netcostsig/1"

# Bump whenever the significance engine's orchestration logic changes in a way that can
# alter a computed value. The analogue of a code git SHA for the engine; explicit and
# stable so derived identity never depends on the wall clock or a random value.
NETCOSTSIG_ENGINE_VERSION = "netcostsig-engine/1"

# Bump whenever Phase 32's *statistical method* changes - the one-sample test statistic
# ``t = (net_mean - 0) / (net_volatility / sqrt(n))``, the one-sided upper-tailed
# large-sample p-value ``1 - Φ(t)``, the zero-volatility guard, or the source-status
# gating. Folded into ``config_hash`` alongside the normal-primitive version, so a
# method change is a new, distinguishable engine version (§13).
NETCOSTSIG_METHOD_VERSION = "netcostsig-method/1"

# Bump whenever the *reused* deterministic exact-``Decimal`` standard-normal primitive
# changes - here only the ``Φ`` CDF of :mod:`quantforge._stats.normal` (Phase 32 uses no
# ``Z⁻¹``). Folded into ``config_hash`` so a change to how the p-value's ``Φ`` is
# computed is a new, distinguishable engine version. Phase 32 reuses that primitive
# verbatim; this version string pins *which* primitive was used, never a copy of it.
NETCOSTSIG_NORMAL_VERSION = "netcostsig-normal/1"

# The pinned decimal context for all significance arithmetic. Precision 34 with banker's
# rounding - identical to every prior derived layer. Applied only via an explicit
# ``localcontext``, never the ambient process context, so results are deterministic
# regardless of caller decimal state.
_DEFAULT_DECIMAL_PRECISION = 34
_DEFAULT_DECIMAL_ROUNDING = ROUND_HALF_EVEN


def default_decimal_context() -> Context:
    """Return a fresh copy of the pinned net-of-cost-significance decimal context.

    A new instance each call so a caller can never mutate the shared context and perturb
    determinism. Precision 34, ``ROUND_HALF_EVEN``.
    """
    return Context(prec=_DEFAULT_DECIMAL_PRECISION, rounding=_DEFAULT_DECIMAL_ROUNDING)


@dataclass(frozen=True, slots=True)
class NetOfCostSignificanceEngineVersion:
    """Immutable identity of the significance-engine logic + config (§13).

    Attributes
    ----------
    code_version:
        Revision string for the engine logic (git SHA in practice).
    method_version:
        Revision string for Phase 32's own statistical method (the one-sample test
        statistic, the one-sided p-value, the guards); folded into ``config_hash`` so a
        method change is a new version.
    normal_version:
        Revision string for the reused deterministic exact-``Decimal`` standard-normal
        primitive (the ``Φ`` CDF); folded into ``config_hash`` so a change to how the
        p-value's ``Φ`` is computed is a new version.
    decimal_precision / decimal_rounding:
        The pinned decimal context folded into ``config_hash`` (every computed value can
        round), so any change to it is a new version.
    """

    code_version: str = NETCOSTSIG_ENGINE_VERSION
    method_version: str = NETCOSTSIG_METHOD_VERSION
    normal_version: str = NETCOSTSIG_NORMAL_VERSION
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
    def net_of_cost_significance_engine_version_id(self) -> str:
        """Deterministic id: ``sha256(code_version, config_hash)`` (§9)."""
        payload = f"{self.code_version}\x00{self.config_hash}".encode()
        return f"sha256:{sha256_hex(payload)}"

    def decimal_context(self) -> Context:
        """The :class:`decimal.Context` this version pins for significance math."""
        return Context(prec=self.decimal_precision, rounding=self.decimal_rounding)
