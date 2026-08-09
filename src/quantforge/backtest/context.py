"""The frozen, PIT-only ``AsOfContext`` capability object (proposal §A, BT-2).

This is the structural enforcement of "no look-ahead" (proposal §A; analysis rows 1,
2). A strategy — and, in v1, the engine's own signal resolution — never touches a
:class:`~quantforge.workspace.Workspace`, a raw store, a :class:`RebalanceSchedule`, or
a settable ``as_of``. It sees only an :class:`AsOfContext`: a capability object the
engine constructs **once per rebalance**, bound to a single decision instant ``T``,
whose every accessor is *pre-bound* to ``T`` and takes **no** ``as_of`` argument.

Two invariants make look-ahead hard to *express*, not merely discouraged:

* **No settable time (BT-2).** There is no method that accepts a future date. The only
  temporal freedom — choosing an accounting :class:`~quantforge.panel.axis.PeriodAxis`
  or a historical :class:`~quantforge.market.axis.PriceAxis` — is upper-bounded by ``T``
  *inside* the underlying ``*_as_of`` accessors: a series cell past ``T`` comes back
  ``UNDEFINED`` / ``not_knowable_yet`` via the existing availability gate, never a
  value.
* **Type-level PIT lock (BT-2).** Every accessor returns a ``Pit*`` type
  (:class:`PitPanel`, :class:`PitFactor`, :class:`PitMetricValue`, :class:`PitPrice`,
  :class:`PitPriceSeries`) or a PIT :class:`ConstructionResult`. A ``Revised*`` type
  requires a :class:`DatasetVersion` argument this context never exposes, so revised
  data is unreachable from inside the strategy boundary (reusing invariant 30's existing
  type separation — Phase 12 adds no new mechanism, it just declines to hand over the
  revised door).

The context is a thin, read-only delegate: it composes the existing Phase 7/8/9/10/11
engines through their public ``*_as_of`` accessors (proposal §J) and introduces no new
resolution logic. It is deliberately *not* a dataclass with public mutable state — it
holds the engines and the single bound ``as_of`` privately, exposes them only through
methods that cannot widen the boundary, and is safe to hand to untrusted strategy code.
"""

from __future__ import annotations

from datetime import datetime

from quantforge.availability.timestamps import ensure_aware_utc
from quantforge.factors.engine import FactorEngine
from quantforge.factors.model import PitFactor
from quantforge.factors.transform import Transform
from quantforge.factors.universe import Universe
from quantforge.market.axis import PriceAxis
from quantforge.market.engine import PriceEngine
from quantforge.market.model import PriceField
from quantforge.market.result import PitPrice, PitPriceSeries
from quantforge.metrics.model import MetricPeriod, PitMetricValue
from quantforge.panel.axis import PeriodAxis
from quantforge.panel.derive import Derivation
from quantforge.panel.engine import PanelEngine
from quantforge.panel.model import PitPanel
from quantforge.universe.builder import UniverseBuilder
from quantforge.universe.construction import ConstructionResult
from quantforge.universe.specification import UniverseSpecification

__all__ = ["AsOfContext"]


class AsOfContext:
    """A read-only, PIT-only view of the world at a single decision instant ``T``.

    Constructed by the :class:`~quantforge.backtest.engine.BacktestEngine` once per
    rebalance and bound to that rebalance's ``as_of``. Every accessor delegates to the
    corresponding Phase 7/8/9/10/11 ``*_as_of`` API at the **bound** ``as_of`` and
    returns the ``Pit*`` type — the strategy can neither pass its own ``as_of`` nor
    obtain a ``Revised*`` result (BT-2). The bound instant is exposed read-only as
    :attr:`as_of` for provenance, but nothing accepts a *different* instant.
    """

    __slots__ = (
        "_as_of",
        "_factor_engine",
        "_panel_engine",
        "_price_engine",
        "_universe_builder",
    )

    def __init__(
        self,
        *,
        as_of: datetime,
        panel_engine: PanelEngine,
        factor_engine: FactorEngine,
        price_engine: PriceEngine,
        universe_builder: UniverseBuilder,
    ) -> None:
        # Normalize the bound instant once, at construction, through the same Phase 5
        # choke point every accessor relies on — a naive ``as_of`` is rejected here,
        # never silently treated as UTC (invariant 15).
        self._as_of = ensure_aware_utc(as_of)
        self._panel_engine = panel_engine
        self._factor_engine = factor_engine
        self._price_engine = price_engine
        self._universe_builder = universe_builder

    @property
    def as_of(self) -> datetime:
        """The single decision instant this context is bound to (read-only)."""
        return self._as_of

    # -- fundamentals (Phase 7/8/10, §C) ------------------------------------

    def universe(self, specification: UniverseSpecification) -> ConstructionResult:
        """The PIT universe membership known at ``T`` (Phase 9 ``build_as_of``, §E).

        Rebuilds ``specification`` at the bound ``as_of`` — the survivorship-free
        membership: it includes filers later delisted and excludes filers not yet
        public at ``T`` (proposal §E). Returns the PIT :class:`ConstructionResult`; the
        strategy cannot ask for membership at any other instant.
        """
        return self._universe_builder.build_as_of(specification, self._as_of)

    def panel(
        self,
        metric_key: str,
        universe: Universe,
        axis: PeriodAxis,
        *,
        derivation: Derivation | None = None,
    ) -> PitPanel:
        """The cross-sectional fundamental matrix at ``T`` (``panel_across``, §C).

        One ``metric_key`` over every universe member across the accounting ``axis``,
        all resolved at the bound ``as_of``. An ``UNDEFINED`` cell stays ``UNDEFINED``
        (never imputed). Returns a :class:`PitPanel`.
        """
        return self._panel_engine.panel_across(
            metric_key, universe, axis, self._as_of, derivation=derivation
        )

    def factor(
        self,
        metric_key: str,
        universe: Universe,
        period: MetricPeriod,
        *,
        transform: Transform | None = None,
    ) -> PitFactor:
        """The cross-sectional factor vector at ``T`` (``factor_as_of``, §C).

        One ``metric_key`` for every universe member at one accounting ``period``,
        resolved at the bound ``as_of``. Returns a :class:`PitFactor`.
        """
        return self._factor_engine.factor_as_of(
            metric_key, universe, period, self._as_of, transform=transform
        )

    def metric(
        self, cik: str | int, metric_key: str, period: MetricPeriod
    ) -> PitMetricValue:
        """One scalar metric for one filer at ``T`` (``metric_as_of``, §C)."""
        return self._factor_engine.metric_engine.metric_as_of(
            metric_key, cik, period, self._as_of
        )

    # -- market prices (Phase 11, §B) ---------------------------------------

    def price(
        self,
        security_id: str,
        trading_date: str,
        *,
        field: PriceField = PriceField.CLOSE,
    ) -> PitPrice:
        """The PIT spot price for one security on ``trading_date``, known at ``T`` (§B).

        Resolves via Phase 11 ``price_as_of`` at the bound ``as_of``: a bar whose
        availability is after ``T`` is not returned as a value (fail-closed). Returns a
        :class:`PitPrice` (``KNOWN`` with provenance, or ``UNDEFINED``).
        """
        return self._price_engine.price_as_of(
            security_id, trading_date, self._as_of, field=field
        )

    def price_series(
        self,
        security_id: str,
        axis: PriceAxis,
        *,
        field: PriceField = PriceField.CLOSE,
    ) -> PitPriceSeries:
        """The PIT unadjusted price series over ``axis``, all known at ``T`` (§B).

        Every cell is availability-gated at the bound ``as_of`` — a date past ``T``
        yields a ``not_knowable_yet`` cell, never a value. Returns a
        :class:`PitPriceSeries` (unadjusted; the accounting book value, §D).
        """
        return self._price_engine.price_series_as_of(
            security_id, axis, self._as_of, field=field
        )

    def adjusted_series(
        self,
        security_id: str,
        axis: PriceAxis,
        *,
        field: PriceField = PriceField.CLOSE,
    ) -> PitPriceSeries:
        """The PIT split/dividend-**adjusted** signal series over ``axis`` (§B).

        Phase 11's already-PIT-gated adjusted view — only corporate actions whose
        availability is ``<= T`` participate, so no future or revised adjustment can
        leak in. This is a **signal-only** view (e.g. momentum on an adjusted series);
        it is never the accounting book value (proposal §D rule 4). Returns a
        :class:`PitPriceSeries`.
        """
        return self._price_engine.adjusted_series_as_of(
            security_id, axis, self._as_of, field=field
        )
