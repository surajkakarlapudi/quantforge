"""The declarative, content-addressed experiment sweep (locked §3.1, §3.2, D7).

An **experiment** is a declarative parameter sweep over a *base*
:class:`~quantforge.backtest.spec.BacktestSpecification` — never a callback, a
subclass, or arbitrary Python (locked D1). This is the Phase 13 analogue of a
:class:`~quantforge.backtest.spec.BacktestSpecification`: a frozen request whose
identity is a pure content hash of *what was declared*. The engine expands and
interprets it; it never executes code. That is what keeps every child ``backtest_id``
— and therefore the whole experiment — an honest, reproducible identity.

The pieces, both frozen (``@dataclass(frozen=True, slots=True)``):

* :class:`SweepAxis` — one sweepable parameter and its ordered set of allowed values.
  ``parameter`` must be a member of the **closed v1 vocabulary** (locked D7); anything
  else fails closed (we refuse to sweep a parameter we cannot honestly fold into
  ``backtest_id``). ``sweep_axis_id`` is a *set* identity over the sorted canonical
  values, so axis-value order never changes it.
* :class:`ExperimentSpecification` — a name, a base spec, and ``>= 1`` axes on distinct
  parameters. :meth:`expand` is a pure, total Cartesian product: each coordinate is a
  child spec *rebuilt* from the base with the coordinate's parameters substituted (a
  fresh :class:`~quantforge.backtest.spec.StrategySpecification` /
  :class:`~quantforge.backtest.spec.CostModel` / schedule / universe / scalar) — never a
  mutation. **Corpus pins are inherited verbatim** (locked D2): every child carries the
  base's fundamentals + market ``dataset_version_id``s unchanged, so the family is
  comparable by construction.

Nothing here reads a store or the wall clock; both types are pure, reproducible value
objects the engine consumes.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from quantforge.backtest.schedule import RebalanceSchedule
from quantforge.backtest.spec import (
    BacktestSpecification,
    CostModel,
    StrategySpecification,
)
from quantforge.experiment.errors import ExperimentConfigurationError
from quantforge.experiment.identity import experiment_id as _experiment_id
from quantforge.experiment.identity import sweep_axis_id as _sweep_axis_id
from quantforge.metrics.model import MetricPeriod
from quantforge.universe.specification import UniverseSpecification

__all__ = [
    "EXPERIMENT_SPEC_VERSION",
    "SWEEPABLE_PARAMETERS",
    "ExperimentSpecification",
    "SweepAxis",
]

#: The specification-schema version, folded into ``experiment_id`` (locked §3.2). Bump
#: it when the serialized meaning of an experiment changes — never when engine logic
#: changes (that is the engine version). Mirrors ``universe-spec/1`` and
#: ``backtest-stats/1``.
EXPERIMENT_SPEC_VERSION = "experiment/1"

# -- the closed v1 sweepable vocabulary (locked D7) --------------------------
#
# Each is a *declared* parameter that already changes ``backtest_id`` honestly. Anything
# outside this set fails closed until explicitly added (a new parameter hashes
# distinctly — never an edit that changes an existing id).
_PARAM_SELECT_N = "select_n"
_PARAM_RANK = "rank"
_PARAM_SIGNAL = "signal"
_PARAM_PERIOD = "period"
_PARAM_COST_PROP = "cost_model.proportional_bps"
_PARAM_COST_FIXED = "cost_model.fixed_per_order"
_PARAM_SCHEDULE = "schedule"
_PARAM_INITIAL_CAPITAL = "initial_capital"
_PARAM_UNIVERSE = "universe"

#: The closed v1 vocabulary, sorted for stable display (locked D7).
SWEEPABLE_PARAMETERS: tuple[str, ...] = (
    _PARAM_COST_FIXED,
    _PARAM_COST_PROP,
    _PARAM_INITIAL_CAPITAL,
    _PARAM_PERIOD,
    _PARAM_RANK,
    _PARAM_SCHEDULE,
    _PARAM_SELECT_N,
    _PARAM_SIGNAL,
    _PARAM_UNIVERSE,
)

_VOCABULARY = frozenset(SWEEPABLE_PARAMETERS)

_RANK_DIRECTIONS = frozenset({"descending", "ascending"})


def _canonical_json(payload: object) -> str:
    return json.dumps(
        payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )


def _canonical_decimal(value: object, parameter: str, *, allow_zero: bool) -> str:
    """Validate a decimal-string axis value; return its canonical form (fail closed).

    Money/capital axis values are decimal strings end-to-end (no float ever touches a
    monetary quantity — invariant 20), canonicalized so ``"5"`` and ``"5.0"`` fold
    identically. A non-string, non-decimal, non-finite, negative (or, when disallowed,
    zero) value is a configuration defect, raised.
    """
    if not isinstance(value, str) or not value:
        raise ExperimentConfigurationError(
            f"axis {parameter!r} value must be a non-empty decimal string, got "
            f"{value!r}"
        )
    try:
        parsed = Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise ExperimentConfigurationError(
            f"axis {parameter!r} value {value!r} is not a valid decimal string"
        ) from exc
    if not parsed.is_finite():
        raise ExperimentConfigurationError(
            f"axis {parameter!r} value {value!r} must be finite"
        )
    if parsed < 0:
        raise ExperimentConfigurationError(
            f"axis {parameter!r} value {value!r} must not be negative"
        )
    if not allow_zero and parsed == 0:
        raise ExperimentConfigurationError(
            f"axis {parameter!r} value {value!r} must be strictly positive"
        )
    return str(parsed)


def _canonical_value(parameter: str, value: object) -> str:
    """The canonical string form of one axis value, validated per parameter.

    Fail-closed and total over the closed v1 vocabulary (locked D7): a value of the
    wrong type for its parameter raises. The returned string is what enters both the
    axis identity (sorted, as a set) and a coordinate label — never the raw object — so
    two equal values always fold identically regardless of construction.
    """
    if parameter == _PARAM_SELECT_N:
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            raise ExperimentConfigurationError(
                f"axis {parameter!r} value must be a positive int, got {value!r}"
            )
        return str(value)
    if parameter == _PARAM_RANK:
        if not isinstance(value, str) or value not in _RANK_DIRECTIONS:
            raise ExperimentConfigurationError(
                f"axis {parameter!r} value must be one of {sorted(_RANK_DIRECTIONS)}, "
                f"got {value!r}"
            )
        return value
    if parameter == _PARAM_SIGNAL:
        if not isinstance(value, str) or not value:
            raise ExperimentConfigurationError(
                f"axis {parameter!r} value must be a non-empty metric key, got "
                f"{value!r}"
            )
        return value
    if parameter == _PARAM_PERIOD:
        if not isinstance(value, MetricPeriod):
            raise ExperimentConfigurationError(
                f"axis {parameter!r} value must be a MetricPeriod, got {value!r}"
            )
        return _canonical_json(value.to_dict())
    if parameter in (_PARAM_COST_PROP, _PARAM_COST_FIXED):
        return _canonical_decimal(value, parameter, allow_zero=True)
    if parameter == _PARAM_INITIAL_CAPITAL:
        return _canonical_decimal(value, parameter, allow_zero=False)
    if parameter == _PARAM_SCHEDULE:
        if not isinstance(value, RebalanceSchedule):
            raise ExperimentConfigurationError(
                f"axis {parameter!r} value must be a RebalanceSchedule, got {value!r}"
            )
        return value.schedule_id
    if parameter == _PARAM_UNIVERSE:
        if not isinstance(value, UniverseSpecification):
            raise ExperimentConfigurationError(
                f"axis {parameter!r} value must be a UniverseSpecification, got "
                f"{value!r}"
            )
        return value.specification_id
    # Unreachable: SweepAxis validates ``parameter`` against the vocabulary first.
    raise ExperimentConfigurationError(
        f"parameter {parameter!r} is not in the closed v1 sweep vocabulary"
    )


@dataclass(frozen=True, slots=True)
class SweepAxis:
    """One sweepable parameter and its ordered set of allowed values (locked §3.1).

    ``parameter`` must be a member of the closed v1 vocabulary
    (:data:`SWEEPABLE_PARAMETERS`, locked D7). ``values`` is ordered (load-bearing for
    enumeration only) and validated at construction: an empty axis, a duplicate value
    (by canonical form), or a value of the wrong type for the parameter fails closed.
    ``sweep_axis_id`` is a *set* identity over the sorted canonical values, so the
    family an axis generates — and its id — is independent of the value order supplied.
    """

    parameter: str
    values: tuple[object, ...]

    def __post_init__(self) -> None:
        if self.parameter not in _VOCABULARY:
            raise ExperimentConfigurationError(
                f"sweep parameter {self.parameter!r} is not in the closed v1 "
                f"vocabulary {sorted(_VOCABULARY)}; extending the set is an explicit "
                "future change, never an implicit fallback (locked D7)"
            )
        if not self.values:
            raise ExperimentConfigurationError(
                f"sweep axis {self.parameter!r} must enumerate at least one value; an "
                "empty axis is a configuration bug"
            )
        seen: set[str] = set()
        for value in self.values:
            canonical = _canonical_value(self.parameter, value)
            if canonical in seen:
                raise ExperimentConfigurationError(
                    f"sweep axis {self.parameter!r} contains a duplicate value "
                    f"{value!r} (canonical {canonical!r}); each axis value must be "
                    "distinct"
                )
            seen.add(canonical)

    def canonical_values(self) -> tuple[str, ...]:
        """The axis values in their validated canonical string form, input order."""
        return tuple(_canonical_value(self.parameter, v) for v in self.values)

    @property
    def sweep_axis_id(self) -> str:
        """The content-addressed axis id (``sha256:``) over the *sorted* values."""
        return _sweep_axis_id(self.parameter, sorted(self.canonical_values()))

    def to_dict(self) -> dict[str, object]:
        return {
            "sweep_axis_id": self.sweep_axis_id,
            "parameter": self.parameter,
            "values": list(self.canonical_values()),
        }


@dataclass(frozen=True, slots=True)
class ExperimentSpecification:
    """A declarative, content-addressed parameter sweep over a base spec (§3.2).

    ``base`` is a fully pinned :class:`~quantforge.backtest.spec.BacktestSpecification`;
    every child inherits its two corpus pins verbatim (locked D2). ``axes`` is a tuple
    of ``>= 1`` :class:`SweepAxis` on *distinct* parameters (two axes on one parameter
    is an ambiguous product, raised). Constructing this reads no store and no wall
    clock; it validates its own shape at construction, exactly as the backtest/universe
    layers refuse a misconfigured request.
    """

    name: str
    base: BacktestSpecification
    axes: tuple[SweepAxis, ...]
    spec_version: str = EXPERIMENT_SPEC_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name:
            raise ExperimentConfigurationError(
                "an experiment must have a non-empty name"
            )
        if not isinstance(self.base, BacktestSpecification):
            raise ExperimentConfigurationError(
                "experiment.base must be a fully pinned BacktestSpecification"
            )
        if not self.axes:
            raise ExperimentConfigurationError(
                "an experiment must declare at least one sweep axis; a zero-axis "
                "experiment is a single backtest, not a sweep"
            )
        parameters: set[str] = set()
        for axis in self.axes:
            if not isinstance(axis, SweepAxis):
                raise ExperimentConfigurationError(
                    "each experiment axis must be a SweepAxis"
                )
            if axis.parameter in parameters:
                raise ExperimentConfigurationError(
                    f"two axes target the same parameter {axis.parameter!r}; the "
                    "Cartesian product would be ambiguous"
                )
            parameters.add(axis.parameter)

    def sorted_axis_ids(self) -> tuple[str, ...]:
        """The axis ids sorted — a set identity, order-independent (locked §4)."""
        return tuple(sorted(axis.sweep_axis_id for axis in self.axes))

    def experiment_id(self, *, risk_free_per_period: str, periods_per_year: str) -> str:
        """The content-addressed experiment id under a given run convention (§4).

        The annualization run convention (locked D5) is folded into identity, so two
        experiments identical except for their convention get distinct ids — they
        report distinctly-annualized statistics and are therefore materially different.
        """
        return _experiment_id(
            name=self.name,
            spec_version=self.spec_version,
            base_request=self.base.to_dict(),
            sorted_axis_ids=list(self.sorted_axis_ids()),
            risk_free_per_period=risk_free_per_period,
            periods_per_year=periods_per_year,
        )

    def expand(
        self,
    ) -> tuple[tuple[tuple[tuple[str, str], ...], BacktestSpecification], ...]:
        """Expand the sweep into its deterministic family of child specs (§3.2).

        A pure, total Cartesian product across axes: the family size is
        ``∏ len(axis.values)``. Each element is ``(coordinate, child_spec)`` where the
        coordinate is a ``parameter``-sorted tuple of ``(parameter, canonical-value)``
        pairs and the child spec is ``base`` *rebuilt* with those parameters substituted
        (never mutated). Both corpus pins are inherited verbatim (locked D2). The family
        is returned in a deterministic sort over the coordinates, so enumeration order
        never depends on axis declaration order or Python's iteration order.
        """
        # Iterate axes in a stable order (by parameter) so the product is deterministic.
        ordered_axes = sorted(self.axes, key=lambda a: a.parameter)
        combinations: list[list[tuple[str, object, str]]] = [[]]
        for axis in ordered_axes:
            canon = axis.canonical_values()
            combinations = [
                [*prefix, (axis.parameter, value, canonical)]
                for prefix in combinations
                for value, canonical in zip(axis.values, canon, strict=True)
            ]

        family: list[tuple[tuple[tuple[str, str], ...], BacktestSpecification]] = []
        for combo in combinations:
            raw = {parameter: value for parameter, value, _ in combo}
            coordinate = tuple(
                sorted((parameter, canonical) for parameter, _, canonical in combo)
            )
            family.append((coordinate, self._child_spec(raw)))
        family.sort(key=lambda item: item[0])
        return tuple(family)

    def _child_spec(self, coord: dict[str, object]) -> BacktestSpecification:
        """Rebuild ``base`` with the coordinate's parameters substituted (§3.2).

        Strategy parameters (signal / period / select_n / rank) are folded into one
        fresh :class:`~quantforge.backtest.spec.StrategySpecification`; cost parameters
        into one fresh :class:`~quantforge.backtest.spec.CostModel`; the remaining
        object/scalar parameters are substituted directly. Anything not on an axis
        keeps the base value. Corpus pins and accounting/base-currency are inherited
        verbatim (locked D2); nothing is mutated.
        """
        base = self.base
        strategy = StrategySpecification.rank_select_weight(
            signal=_str_of(coord.get(_PARAM_SIGNAL, base.strategy.signal_metric_key)),
            period=_period_of(coord.get(_PARAM_PERIOD, base.strategy.signal_period)),
            select=(
                f"top_n:{_int_of(coord.get(_PARAM_SELECT_N, base.strategy.select_n))}"
            ),
            rank=_str_of(coord.get(_PARAM_RANK, base.strategy.rank_direction)),
        )
        cost_model = CostModel(
            proportional_bps=_str_of(
                coord.get(_PARAM_COST_PROP, base.cost_model.proportional_bps)
            ),
            fixed_per_order=_str_of(
                coord.get(_PARAM_COST_FIXED, base.cost_model.fixed_per_order)
            ),
        )
        schedule = coord.get(_PARAM_SCHEDULE, base.schedule)
        assert isinstance(schedule, RebalanceSchedule)
        universe = coord.get(_PARAM_UNIVERSE, base.universe)
        assert isinstance(universe, UniverseSpecification)
        initial_capital = _str_of(
            coord.get(_PARAM_INITIAL_CAPITAL, base.initial_capital)
        )
        return BacktestSpecification(
            strategy=strategy,
            schedule=schedule,
            universe=universe,
            dataset_version_id=base.dataset_version_id,
            market_dataset_version_id=base.market_dataset_version_id,
            cost_model=cost_model,
            accounting=base.accounting,
            initial_capital=initial_capital,
            base_currency=base.base_currency,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "spec_version": self.spec_version,
            "name": self.name,
            "base": self.base.to_dict(),
            "axes": [axis.to_dict() for axis in self.axes],
            "axis_ids": list(self.sorted_axis_ids()),
        }


def _str_of(value: object) -> str:
    assert isinstance(value, str)
    return value


def _int_of(value: object) -> int:
    assert isinstance(value, int)
    return value


def _period_of(value: object) -> MetricPeriod:
    assert isinstance(value, MetricPeriod)
    return value
