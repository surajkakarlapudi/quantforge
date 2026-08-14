"""The net-of-cost transformation version (Phase 31, §13).

Per data-model §9 a ``TransformationVersion`` identifies the deterministic code+config
that turns inputs into derived state:

    net_of_cost_engine_version_id = hash(code_version, config_hash)

For Phase 31 the "transformation" is the **net-of-cost engine** that turns a declarative
:class:`~quantforge.netcost.spec.NetOfCostSpecification` (naming exactly one sealed
:class:`~quantforge.stability.result.WalkForwardStability` and a declared linear
transaction-cost rate) into a sealed
:class:`~quantforge.netcost.result.NetOfCostPerformance` - the gross out-of-sample
return series (carried transitively from the walk-forward beneath the stability record)
charged a per-window one-way turnover cost, summarized net-of-cost with the *reused*
Phase 19 series summary, plus the parameter-free break-even cost rate. This module pins
that engine logic with a stable version id, following the exact pattern of
:class:`~quantforge.calsig.version.CalibrationSignificanceEngineVersion` (the id is a
``sha256:`` of the content; nothing depends on the wall clock).

Three properties are load-bearing (data-model invariants 19-21):

* **The pinned decimal context is part of the version.** All net-of-cost arithmetic -
  the per-period cost ``cost_rate · turnover`` charged at each realized window's first
  out-of-sample period, the net return series, the aggregate cost drag, and the
  break-even ``Σ gross / Σ turnover`` (one ``Decimal`` division) - runs under an
  explicit :class:`decimal.Context` (precision + rounding). It is folded into
  ``config_hash``, so a change to it necessarily produces a new, distinguishable
  ``net_of_cost_engine_version_id``. The default is **precision 34,
  ``ROUND_HALF_EVEN``** - identical to every prior derived layer.
* **The method + reused-summary versions are part of the version.** Phase 31 computes
  its own self-contained cost-accounting method (:data:`NETCOST_METHOD_VERSION`) atop
  the *reused* Phase 19 series summary (:data:`NETCOST_SUMMARY_VERSION`:
  :func:`quantforge.factorportfolio.stats.series_summary`,
  the identical population-volatility / annualized-Sharpe convention Phase 22 used for
  the gross summary, so the net Sharpe is directly comparable to the gross Sharpe). Both
  are folded into ``config_hash``, so a change to *either* yields a new, distinguishable
  engine id.
* **The version depends only on code + config**, never on wall-clock time, a random
  value, or input ordering (invariant 21).

Changing the net-of-cost logic in a way that can alter a computed value must bump
:data:`NETCOST_ENGINE_VERSION` (the code version), :data:`NETCOST_METHOD_VERSION` (the
cost-accounting method), or :data:`NETCOST_SUMMARY_VERSION` (the reused series-summary
method - which is owned by Phase 19 and pinned here by reference, never re-implemented).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Context

from quantforge.factorportfolio.version import FACTORPORTFOLIO_FORMULA_VERSION
from quantforge.sec.artifacts import sha256_hex

__all__ = [
    "NETCOST_ENGINE_VERSION",
    "NETCOST_METHOD_VERSION",
    "NETCOST_SPEC_VERSION",
    "NETCOST_SUMMARY_VERSION",
    "NetOfCostEngineVersion",
    "default_decimal_context",
]

# The specification-schema version, folded into ``net_of_cost_id`` (§13). Bump it when
# the serialized meaning of a request changes - never when engine logic changes (that is
# ``NETCOST_ENGINE_VERSION``). Shares the ``netcost/1`` string with the identity domain
# tag by construction (the prior-phase precedent).
NETCOST_SPEC_VERSION = "netcost/1"

# Bump whenever the net-of-cost engine's orchestration logic changes in a way that can
# alter a computed value. The analogue of a code git SHA for the (as-yet uncommitted)
# engine; explicit and stable so derived identity never depends on the wall clock or a
# random value.
NETCOST_ENGINE_VERSION = "netcost-engine/1"

# Bump whenever Phase 31's *cost-accounting method* changes - the per-period cost
# placement (``cost_rate · turnover`` charged at each realized window's first
# out-of-sample period), the net return series construction, the cost-drag definition,
# or the break-even ``Σ gross / Σ turnover``. Folded into ``config_hash`` alongside the
# reused-summary version, so a method change is a new, distinguishable engine version
# (§13).
NETCOST_METHOD_VERSION = "netcost-method/1"

# Bump whenever the *reused* Phase 19 series-summary method changes - the
# population-volatility / annualized-Sharpe / t-statistic convention Phase 31 applies to
# the net (and, verbatim from the source, the gross) return series. This is Phase 19's
# ``factorportfolio-stats/1``, pinned here **by reference** so a Phase 31 record folds
# *which* summary method produced its Sharpe; Phase 31 never re-implements it (the
# identical primitive Phase 22 used for the gross summary, so net and gross are
# comparable).
NETCOST_SUMMARY_VERSION = FACTORPORTFOLIO_FORMULA_VERSION

# The pinned decimal context for all net-of-cost arithmetic. Precision 34 with banker's
# rounding - identical to every prior derived layer. Applied only via an explicit
# ``localcontext``, never the ambient process context, so results are deterministic
# regardless of caller decimal state.
_DEFAULT_DECIMAL_PRECISION = 34
_DEFAULT_DECIMAL_ROUNDING = ROUND_HALF_EVEN


def default_decimal_context() -> Context:
    """Return a fresh copy of the pinned net-of-cost decimal context.

    A new instance each call so a caller can never mutate the shared context and perturb
    determinism. Precision 34, ``ROUND_HALF_EVEN``.
    """
    return Context(prec=_DEFAULT_DECIMAL_PRECISION, rounding=_DEFAULT_DECIMAL_ROUNDING)


@dataclass(frozen=True, slots=True)
class NetOfCostEngineVersion:
    """Immutable identity of the net-of-cost-engine logic + config (§13).

    Attributes
    ----------
    code_version:
        Revision string for the engine logic (git SHA in practice).
    method_version:
        Revision string for Phase 31's own cost-accounting method (the per-period cost
        placement, the net series, the cost drag, the break-even ratio); folded into
        ``config_hash`` so a method change is a new version.
    summary_version:
        Revision string for the reused Phase 19 series-summary method (the net / gross
        Sharpe convention); folded into ``config_hash`` so a change to how the Sharpe is
        computed is a new version. Owned by Phase 19; pinned here by reference.
    decimal_precision / decimal_rounding:
        The pinned decimal context folded into ``config_hash`` (every computed value can
        round), so any change to it is a new version.
    """

    code_version: str = NETCOST_ENGINE_VERSION
    method_version: str = NETCOST_METHOD_VERSION
    summary_version: str = NETCOST_SUMMARY_VERSION
    decimal_precision: int = _DEFAULT_DECIMAL_PRECISION
    decimal_rounding: str = _DEFAULT_DECIMAL_ROUNDING

    @property
    def config_hash(self) -> str:
        """Deterministic ``sha256:`` of decimal-context + method + reused summary."""
        payload = (
            f"prec={self.decimal_precision}\x00round={self.decimal_rounding}"
            f"\x00method={self.method_version}"
            f"\x00summary={self.summary_version}"
        )
        return f"sha256:{sha256_hex(payload.encode('utf-8'))}"

    @property
    def net_of_cost_engine_version_id(self) -> str:
        """Deterministic id: ``sha256(code_version, config_hash)`` (§9)."""
        payload = f"{self.code_version}\x00{self.config_hash}".encode()
        return f"sha256:{sha256_hex(payload)}"

    def decimal_context(self) -> Context:
        """The :class:`decimal.Context` this version pins for net-of-cost math."""
        return Context(prec=self.decimal_precision, rounding=self.decimal_rounding)
