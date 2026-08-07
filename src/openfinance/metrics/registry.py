"""The built-in, versioned, declarative starter formulas (§6.5, Decision D6).

:class:`FormulaRegistry` holds the eight approved starter metrics as immutable
:class:`~openfinance.metrics.formula.FormulaDefinition`s. Each is pure declarative
data — an ordered ``(taxonomy, local_name)`` candidate list per operand, an
operation tree, a primary period type, and an output unit — so its ``formula_id``
is a content hash and any change is a new version, never a silent edit (§8).

All eight ship ``confidence = "unvalidated"`` (§18): the *arithmetic* is exact, but
the concept-selection candidate lists are heuristics reflecting common ``us-gaap``
usage until validated against real filings — mirroring how ``AvailabilityPolicy``
ships ``unvalidated``. **No company data is ever hardcoded**; no formula names a
CIK or ticker. Looking up an unknown ``metric_key`` fails closed with
:class:`FormulaConfigurationError` (our-bug surfaced, never a guessed formula).
"""

from __future__ import annotations

from openfinance.canonical.taxonomy import Taxonomy
from openfinance.metrics.errors import FormulaConfigurationError
from openfinance.metrics.formula import (
    ConceptCandidate,
    Div,
    FormulaDefinition,
    InputBinding,
    Ref,
    Sub,
)
from openfinance.metrics.units import UnitExpectation
from openfinance.xbrl.contexts import PeriodType

__all__ = ["FormulaRegistry", "builtin_formulas"]


def _gaap(local_name: str) -> ConceptCandidate:
    """A single ``us-gaap`` candidate concept (the common case)."""
    return ConceptCandidate(Taxonomy.US_GAAP, local_name)


def _gaap_list(*local_names: str) -> tuple[ConceptCandidate, ...]:
    """An ordered tuple of ``us-gaap`` candidates (highest priority first)."""
    return tuple(_gaap(name) for name in local_names)


# Revenue's ordered candidate list is shared by four formulas (§6.5); declared once
# so every use hashes identically and a change updates them together, by design.
_REVENUE_CANDIDATES = _gaap_list(
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "Revenues",
    "SalesRevenueNet",
)


def _instant(name: str, candidates: tuple[ConceptCandidate, ...]) -> InputBinding:
    """A consolidated, monetary, instant balance-sheet input."""
    return InputBinding(
        name=name,
        concept_candidates=candidates,
        period_kind=PeriodType.INSTANT,
        unit_expectation=UnitExpectation.MONETARY,
    )


def _duration(name: str, candidates: tuple[ConceptCandidate, ...]) -> InputBinding:
    """A consolidated, monetary, duration income/flow input."""
    return InputBinding(
        name=name,
        concept_candidates=candidates,
        period_kind=PeriodType.DURATION,
        unit_expectation=UnitExpectation.MONETARY,
    )


def builtin_formulas() -> tuple[FormulaDefinition, ...]:
    """Construct the eight approved starter formulas (§6.5, Decision D6).

    A fresh tuple each call (no shared mutable state); ids are content-addressed and
    therefore stable across calls.
    """
    return (
        # current_ratio = AssetsCurrent / LiabilitiesCurrent  (INSTANT, pure)
        FormulaDefinition(
            metric_key="current_ratio",
            description="Current assets divided by current liabilities.",
            inputs=(
                _instant("current_assets", _gaap_list("AssetsCurrent")),
                _instant("current_liabilities", _gaap_list("LiabilitiesCurrent")),
            ),
            operation=Div(Ref("current_assets"), Ref("current_liabilities")),
            period_type=PeriodType.INSTANT,
            output_unit=UnitExpectation.PURE,
        ),
        # quick_ratio = (AssetsCurrent - Inventory) / LiabilitiesCurrent
        FormulaDefinition(
            metric_key="quick_ratio",
            description=(
                "Current assets less inventory, divided by current liabilities."
            ),
            inputs=(
                _instant("current_assets", _gaap_list("AssetsCurrent")),
                _instant(
                    "inventory",
                    _gaap_list("InventoryNet", "InventoryFinishedGoodsNetOfReserves"),
                ),
                _instant("current_liabilities", _gaap_list("LiabilitiesCurrent")),
            ),
            operation=Div(
                Sub(Ref("current_assets"), Ref("inventory")),
                Ref("current_liabilities"),
            ),
            period_type=PeriodType.INSTANT,
            output_unit=UnitExpectation.PURE,
        ),
        # working_capital = AssetsCurrent - LiabilitiesCurrent  (INSTANT, USD)
        FormulaDefinition(
            metric_key="working_capital",
            description="Current assets minus current liabilities (a money amount).",
            inputs=(
                _instant("current_assets", _gaap_list("AssetsCurrent")),
                _instant("current_liabilities", _gaap_list("LiabilitiesCurrent")),
            ),
            operation=Sub(Ref("current_assets"), Ref("current_liabilities")),
            period_type=PeriodType.INSTANT,
            output_unit=UnitExpectation.MONETARY,
        ),
        # gross_margin = (Revenue - CostOfRevenue) / Revenue  (DURATION, pure)
        FormulaDefinition(
            metric_key="gross_margin",
            description="Revenue less cost of revenue, divided by revenue.",
            inputs=(
                _duration("revenue", _REVENUE_CANDIDATES),
                _duration(
                    "cost_of_revenue",
                    _gaap_list(
                        "CostOfRevenue",
                        "CostOfGoodsAndServicesSold",
                        "CostOfGoodsSold",
                    ),
                ),
            ),
            operation=Div(Sub(Ref("revenue"), Ref("cost_of_revenue")), Ref("revenue")),
            period_type=PeriodType.DURATION,
            output_unit=UnitExpectation.PURE,
        ),
        # operating_margin = OperatingIncomeLoss / Revenue  (DURATION, pure)
        FormulaDefinition(
            metric_key="operating_margin",
            description="Operating income divided by revenue.",
            inputs=(
                _duration("operating_income", _gaap_list("OperatingIncomeLoss")),
                _duration("revenue", _REVENUE_CANDIDATES),
            ),
            operation=Div(Ref("operating_income"), Ref("revenue")),
            period_type=PeriodType.DURATION,
            output_unit=UnitExpectation.PURE,
        ),
        # net_margin = NetIncomeLoss / Revenue  (DURATION, pure)
        FormulaDefinition(
            metric_key="net_margin",
            description="Net income divided by revenue.",
            inputs=(
                _duration("net_income", _gaap_list("NetIncomeLoss")),
                _duration("revenue", _REVENUE_CANDIDATES),
            ),
            operation=Div(Ref("net_income"), Ref("revenue")),
            period_type=PeriodType.DURATION,
            output_unit=UnitExpectation.PURE,
        ),
        # debt_to_equity = Liabilities / StockholdersEquity  (INSTANT, pure)
        FormulaDefinition(
            metric_key="debt_to_equity",
            description="Total liabilities divided by stockholders' equity.",
            inputs=(
                _instant("liabilities", _gaap_list("Liabilities")),
                _instant("equity", _gaap_list("StockholdersEquity")),
            ),
            operation=Div(Ref("liabilities"), Ref("equity")),
            period_type=PeriodType.INSTANT,
            output_unit=UnitExpectation.PURE,
        ),
        # asset_turnover = Revenue / Assets  (DURATION revenue ÷ INSTANT ending assets)
        FormulaDefinition(
            metric_key="asset_turnover",
            description=(
                "Revenue over the fiscal span divided by ending total assets "
                "(ending, not average — averaging needs two periods, deferred)."
            ),
            inputs=(
                _duration("revenue", _REVENUE_CANDIDATES),
                _instant("assets", _gaap_list("Assets")),
            ),
            operation=Div(Ref("revenue"), Ref("assets")),
            period_type=PeriodType.DURATION,
            output_unit=UnitExpectation.PURE,
            notes=(
                "Mixed-period: DURATION revenue ÷ INSTANT assets at the span's "
                "period_end (the ending balance, §6.4)."
            ),
        ),
    )


class FormulaRegistry:
    """An immutable, name-indexed registry of :class:`FormulaDefinition`s (§6).

    Defaults to the eight approved starter formulas; a caller may construct one with
    an explicit formula set (e.g. for authoring/inspection tests). Fail-closed on an
    unknown ``metric_key`` — we never synthesize a formula.
    """

    def __init__(self, formulas: tuple[FormulaDefinition, ...] | None = None) -> None:
        defs = formulas if formulas is not None else builtin_formulas()
        by_key: dict[str, FormulaDefinition] = {}
        for definition in defs:
            if definition.metric_key in by_key:
                raise FormulaConfigurationError(
                    f"duplicate metric_key {definition.metric_key!r} in registry"
                )
            by_key[definition.metric_key] = definition
        self._by_key = by_key

    def get(self, metric_key: str) -> FormulaDefinition:
        """Return the formula for ``metric_key`` or fail closed (§6, §13)."""
        try:
            return self._by_key[metric_key]
        except KeyError:
            raise FormulaConfigurationError(
                f"unknown metric_key {metric_key!r}; known: {self.metric_keys()}"
            ) from None

    def has(self, metric_key: str) -> bool:
        return metric_key in self._by_key

    def metric_keys(self) -> tuple[str, ...]:
        """Every registered metric key, sorted (deterministic enumeration)."""
        return tuple(sorted(self._by_key))

    def formulas(self) -> tuple[FormulaDefinition, ...]:
        """Every registered formula, ordered by ``metric_key`` (deterministic)."""
        return tuple(self._by_key[k] for k in self.metric_keys())
