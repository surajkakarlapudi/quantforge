"""The declarative, content-addressed factor-portfolio request (§5.2).

A **factor-portfolio request** names a single characteristic signal (a ``metric_key``
and the explicit :class:`~quantforge.metrics.model.MetricPeriod` it is read for), a
Phase 9 universe specification, a Phase 12 evaluation schedule of ``as_of`` instants
(the rebalance dates ``T``), a forward-return horizon, a quantile count ``Q``, a
leg-weighting scheme, an annualization convention, and the two corpus pins (fundamentals
+ market). Like every request in this project it is a frozen value whose identity is a
pure content hash of *what was declared* - the engine resolves and interprets it; it
never executes caller code (mirrors
:class:`~quantforge.crosssection.spec.CrossSectionalRegressionSpecification`).

The spec validates its own shape at construction (fail closed,
:class:`~quantforge.factorportfolio.errors.FactorPortfolioConfigurationError`): an empty
``name`` / ``signal`` / ``spec_version`` / corpus pin; a ``period`` that is not a
:class:`~quantforge.metrics.model.MetricPeriod`; ``quantiles < 2``; an unknown
``weighting`` scheme; a ``forward_horizon`` not of the form ``"<n>d"`` with ``n >= 1``;
a non-canonical ``risk_free_per_period`` / ``periods_per_year`` decimal string; a
``universe`` / ``schedule`` missing its content-addressed identity. It reads no store
and no wall clock - it cannot know whether the referenced corpora exist (that is the
engine's fail-closed pin-verification step); it validates only the request's internal
shape.

The corpus *content* is folded by
:func:`~quantforge.factorportfolio.identity.factor_portfolio_id` at the engine, from the
declared pins - so the spec is a stable declaration independent of whether the corpora
have been read yet.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING

from quantforge.factorportfolio.errors import FactorPortfolioConfigurationError
from quantforge.factorportfolio.version import FACTORPORTFOLIO_SPEC_VERSION
from quantforge.metrics.model import MetricPeriod
from quantforge.universe.specification import UniverseSpecification

if TYPE_CHECKING:
    from quantforge.backtest.schedule import RebalanceSchedule

__all__ = [
    "WEIGHTING_EQUAL",
    "FactorPortfolioSpecification",
]

#: The single supported forward-horizon representation (§5.2): a trading-day count. A
#: calendar / schedule-step form is out of scope for v1 and hashes distinctly if ever
#: added, so it can never silently reinterpret a stored id. Mirrors Phase 16 / Phase 18
#: verbatim.
_HORIZON_RE = re.compile(r"^([0-9]+)d$")

#: The only leg-weighting scheme a v1 request may declare (D-WEIGHT, §7): equal-weight
#: within each leg. The closed vocabulary ``{"equal"}`` - a future
#: value/rank/proportional scheme hashes distinctly (it is folded into
#: ``factor_portfolio_id``), so it can never silently reinterpret a stored record.
WEIGHTING_EQUAL = "equal"
_WEIGHTINGS = frozenset({WEIGHTING_EQUAL})


def _canonical_decimal(raw: str, *, what: str) -> str:
    """Canonicalize a finite decimal string via ``str(+Decimal(raw))`` (fail closed).

    The annualization inputs (``risk_free_per_period`` / ``periods_per_year``) are
    folded into identity, so they must be canonical: two spellings of the same number
    must yield one id. A non-decimal or non-finite value is a configuration defect,
    raised rather than guessed.
    """
    try:
        value = Decimal(raw)
    except (InvalidOperation, ValueError) as exc:
        raise FactorPortfolioConfigurationError(
            f"{what} {raw!r} must be a finite decimal string"
        ) from exc
    if not value.is_finite():
        raise FactorPortfolioConfigurationError(f"{what} {raw!r} must be finite")
    return str(+value)


@dataclass(frozen=True, slots=True)
class FactorPortfolioSpecification:
    """A declarative, content-addressed factor-portfolio request (§5.2).

    ``signal`` is a Phase 7 ``metric_key``; ``period`` the explicit
    :class:`~quantforge.metrics.model.MetricPeriod` it is read for (never inferred);
    ``universe`` a Phase 9
    :class:`~quantforge.universe.specification.UniverseSpecification`; ``schedule`` a
    Phase 12 :class:`~quantforge.backtest.schedule.RebalanceSchedule` of evaluation
    ``as_of`` instants (the rebalance dates ``T``); ``forward_horizon`` a ``"<n>d"``
    trading-day count; ``quantiles`` the sort granularity ``Q >= 2`` (long = top bucket,
    short = bottom bucket); ``weighting`` the leg-weighting scheme (v1 closed vocabulary
    ``{"equal"}``); ``risk_free_per_period`` / ``periods_per_year`` the annualization
    convention (canonical decimal strings, folded into identity); ``dataset_version_id``
    / ``market_dataset_version_id`` the two corpus pins re-verified at construct
    (P19-1). Constructing this reads no store and no wall clock; it validates its own
    shape, exactly as the backtest / cross-section layers refuse a misconfigured
    request.
    """

    name: str
    signal: str
    period: MetricPeriod
    universe: UniverseSpecification
    # A RebalanceSchedule; annotated via TYPE_CHECKING so mypy sees the real surface
    # while the module avoids a load-time import (validated by duck-typing below).
    schedule: RebalanceSchedule
    forward_horizon: str
    quantiles: int
    dataset_version_id: str
    market_dataset_version_id: str
    weighting: str = WEIGHTING_EQUAL
    risk_free_per_period: str = "0"
    periods_per_year: str = "1"
    spec_version: str = FACTORPORTFOLIO_SPEC_VERSION
    #: The parsed trading-day count - derived at construction, never supplied.
    horizon_days: int = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name:
            raise FactorPortfolioConfigurationError(
                "a factor-portfolio request must have a non-empty name"
            )
        if not isinstance(self.signal, str) or not self.signal:
            raise FactorPortfolioConfigurationError(
                "a factor-portfolio request must name a non-empty signal metric_key"
            )
        if not isinstance(self.period, MetricPeriod):
            raise FactorPortfolioConfigurationError(
                "period must be a MetricPeriod (an explicit fiscal period, never "
                "inferred)"
            )
        if not isinstance(self.universe, UniverseSpecification):
            raise FactorPortfolioConfigurationError(
                "universe must be a UniverseSpecification"
            )
        # The schedule is duck-typed to avoid importing backtest at module load; it must
        # expose the RebalanceSchedule surface the engine relies on.
        if not hasattr(self.schedule, "schedule_id") or not hasattr(
            self.schedule, "as_of_instants"
        ):
            raise FactorPortfolioConfigurationError(
                "schedule must be a RebalanceSchedule (with schedule_id + "
                "as_of_instants)"
            )
        if len(self.schedule.as_of_instants()) == 0:
            raise FactorPortfolioConfigurationError(
                "schedule must enumerate at least one evaluation as_of instant"
            )
        if not isinstance(self.forward_horizon, str):
            raise FactorPortfolioConfigurationError(
                "forward_horizon must be a string of the form '<n>d'"
            )
        match = _HORIZON_RE.match(self.forward_horizon)
        if match is None:
            raise FactorPortfolioConfigurationError(
                f"forward_horizon {self.forward_horizon!r} must be of the form '<n>d' "
                "(a trading-day count)"
            )
        horizon_days = int(match.group(1))
        if horizon_days < 1:
            raise FactorPortfolioConfigurationError(
                "forward_horizon must be at least 1 trading day"
            )
        object.__setattr__(self, "horizon_days", horizon_days)
        # ``bool`` is a subclass of ``int``; reject it explicitly so ``True``/``False``
        # can never masquerade as a quantile count.
        if not isinstance(self.quantiles, int) or isinstance(self.quantiles, bool):
            raise FactorPortfolioConfigurationError("quantiles must be an int")
        if self.quantiles < 2:
            raise FactorPortfolioConfigurationError(
                "quantiles must be at least 2 (a long top bucket and a short bottom "
                "bucket)"
            )
        if self.weighting not in _WEIGHTINGS:
            raise FactorPortfolioConfigurationError(
                f"weighting {self.weighting!r} is not supported; v1 allows only "
                f"{sorted(_WEIGHTINGS)}"
            )
        if not isinstance(self.dataset_version_id, str) or not self.dataset_version_id:
            raise FactorPortfolioConfigurationError(
                "dataset_version_id must be a non-empty fundamentals corpus pin"
            )
        if (
            not isinstance(self.market_dataset_version_id, str)
            or not self.market_dataset_version_id
        ):
            raise FactorPortfolioConfigurationError(
                "market_dataset_version_id must be a non-empty market corpus pin"
            )
        # Canonicalize the annualization decimals in place (they are folded into
        # identity, so two spellings of the same number must yield one id).
        object.__setattr__(
            self,
            "risk_free_per_period",
            _canonical_decimal(self.risk_free_per_period, what="risk_free_per_period"),
        )
        object.__setattr__(
            self,
            "periods_per_year",
            _canonical_decimal(self.periods_per_year, what="periods_per_year"),
        )
        if not isinstance(self.spec_version, str) or not self.spec_version:
            raise FactorPortfolioConfigurationError(
                "spec_version must be a non-empty string"
            )

    def to_dict(self) -> dict[str, object]:
        """The canonical request payload (deterministic; embedded in the sealed record).

        The ``universe`` / ``schedule`` are emitted in their own canonical serialized
        forms; the annualization decimals are already canonicalized.
        """
        return {
            "spec_version": self.spec_version,
            "name": self.name,
            "signal": self.signal,
            "period": self.period.to_dict(),
            "universe": self.universe.to_dict(),
            "schedule": self.schedule.to_dict(),
            "forward_horizon": self.forward_horizon,
            "horizon_days": self.horizon_days,
            "quantiles": self.quantiles,
            "weighting": self.weighting,
            "risk_free_per_period": self.risk_free_per_period,
            "periods_per_year": self.periods_per_year,
            "dataset_version_id": self.dataset_version_id,
            "market_dataset_version_id": self.market_dataset_version_id,
        }
