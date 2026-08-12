"""Date reconstruction: rebuild each strategy's realized OOS return series by date.

This is the heart of Phase 24's alignment, and its one deliberate deviation from the
approved proposal (which aligned strategies by *axis index*). A sealed
:class:`~quantforge.walkforward.result.WalkForwardEvaluation` seals **no dates**: its
per-window ``[test_start, test_end)`` ranges are indices into a complete-case date axis
that the walk computed but did not store, and each strategy has its *own* axis (its
factors' complete-case intersection can differ). Aligning two strategies by shared axis
index would therefore compare returns from different calendar instants whenever their
axes differ. So Phase 24 **reconstructs** each strategy's axis and maps its realized
out-of-sample (OOS) returns back to calendar dates, then aligns each pair by
calendar-date intersection (:mod:`quantforge.comparison.compute`).

For each strategy this module re-resolves the transitive chain the walk pinned -
``optimization_ref -> PortfolioOptimization.risk_model_ref -> FactorRiskModel factor
refs -> FactorPortfolio.per_period`` - verifying every id and ``result_hash`` against
the pin (fail closed on any drift, SC-1), then recomputes the deterministic
complete-case date axis with the **identical** logic the walk-forward engine used
(:meth:`~quantforge.walkforward.engine.WalkForwardEvaluationEngine._known_returns` /
``_common_dates``): the ascending intersection of the ``as_of`` instants where every
factor carries a KNOWN return. Two fail-closed guards bind the reconstruction to the
sealed record so it can never silently drift:

* the reconstructed axis length must equal the record's sealed ``common_periods``;
* concatenating the REALIZED windows' ``oos_returns`` in window order must reproduce the
  record's sealed chained ``oos_returns`` exactly.

Only then is each REALIZED window's ``oos_returns[k]`` mapped to
``common_dates[test_start + k]``, yielding the strategy's ``(as_of -> OOS return)`` map.
The mapping is pure string/set manipulation over already-canonical sealed decimal
strings - no arithmetic, no decimal context, no wall clock, no RNG.
"""

from __future__ import annotations

from dataclasses import dataclass

from quantforge.comparison.errors import ComparisonConsistencyError
from quantforge.factorportfolio.model import FactorPortfolioStatus
from quantforge.factorportfolio.result import FactorPortfolio
from quantforge.factorrisk.result import FactorRiskModel
from quantforge.factors.store import ResearchResultStore
from quantforge.optimization.result import PortfolioOptimization
from quantforge.walkforward.model import WindowStatus
from quantforge.walkforward.result import WalkForwardEvaluation

__all__ = [
    "ReconstructedStrategy",
    "reconstruct_strategy",
]


@dataclass(frozen=True, slots=True)
class ReconstructedStrategy:
    """A strategy's realized OOS returns keyed by reconstructed calendar date.

    ``returns`` maps each realized OOS ``as_of`` instant to the sealed OOS return
    decimal string; ``axis_periods`` is the reconstructed complete-case axis length
    (equal to the record's sealed ``common_periods`` by the drift guard). The pair
    aligner intersects two strategies' ``returns`` maps by calendar date.
    """

    walk_forward_id: str
    returns: dict[str, str]
    axis_periods: int


def reconstruct_strategy(
    evaluation: WalkForwardEvaluation, store: ResearchResultStore
) -> ReconstructedStrategy:
    """Reconstruct one strategy's ``(as_of -> OOS return)`` map (fail closed, SC-1).

    Re-resolves the transitive chain the walk pinned (verifying ids + hashes),
    recomputes the complete-case date axis with the walk-forward engine's logic, guards
    it against the sealed ``common_periods`` and chained ``oos_returns``, and maps each
    REALIZED window's returns onto the axis dates. Any missing / drifted reference, any
    axis-length or window-range disagreement, or any duplicate mapped date is a
    consistency defect and raises rather than producing a silently wrong alignment.
    """
    opt_id, opt_hash = evaluation.optimization_ref
    optimization = _resolve_optimization(store, opt_id, opt_hash)
    risk_id, risk_hash = optimization.risk_model_ref
    model = _resolve_risk_model(store, risk_id, risk_hash)
    factors = [
        _resolve_factor(store, factor_id, factor_hash)
        for _label, factor_id, factor_hash in model.factor_refs
    ]

    # -- complete-case common date axis (identical to the walk-forward engine) --
    known_by_factor = [_known_dates(factor) for factor in factors]
    common_dates = _common_dates(known_by_factor)
    if len(common_dates) != evaluation.common_periods:
        raise ComparisonConsistencyError(
            f"strategy {evaluation.research_result_id!r} reconstructs to "
            f"{len(common_dates)} complete-case period(s) but its sealed record pins "
            f"common_periods={evaluation.common_periods}; the referenced factor chain "
            "has drifted since the walk was sealed (fail closed, SC-1)"
        )

    # -- map each REALIZED window's OOS returns onto the axis dates -------------
    returns: dict[str, str] = {}
    chained: list[str] = []
    for window in evaluation.windows:
        if window.status is not WindowStatus.REALIZED:
            continue
        span = window.test_end - window.test_start
        if span != len(window.oos_returns):
            raise ComparisonConsistencyError(
                f"strategy {evaluation.research_result_id!r} window "
                f"{window.index} spans {span} test period(s) but sealed "
                f"{len(window.oos_returns)} OOS return(s); the record is inconsistent "
                "(fail closed)"
            )
        if window.test_start < 0 or window.test_end > len(common_dates):
            raise ComparisonConsistencyError(
                f"strategy {evaluation.research_result_id!r} window "
                f"{window.index} test range [{window.test_start}, {window.test_end}) "
                f"falls outside the reconstructed axis of {len(common_dates)} "
                "period(s) (fail closed)"
            )
        for offset, value in enumerate(window.oos_returns):
            as_of = common_dates[window.test_start + offset]
            if as_of in returns:
                raise ComparisonConsistencyError(
                    f"strategy {evaluation.research_result_id!r} maps a second OOS "
                    f"return onto as_of {as_of!r}; the sealed windows overlap in test "
                    "range (fail closed)"
                )
            returns[as_of] = value
            chained.append(value)

    # -- bind the reconstruction to the sealed chained OOS series ---------------
    if tuple(chained) != evaluation.oos_returns:
        raise ComparisonConsistencyError(
            f"strategy {evaluation.research_result_id!r} reconstructs a chained OOS "
            "series that disagrees with the sealed record; the window mapping is "
            "inconsistent with the sealed answer (fail closed, SC-1)"
        )
    return ReconstructedStrategy(
        walk_forward_id=evaluation.research_result_id,
        returns=returns,
        axis_periods=len(common_dates),
    )


# -- transitive-chain resolution (fail closed, SC-1) -------------------------


def _resolve_optimization(
    store: ResearchResultStore, optimization_id: str, result_hash: str
) -> PortfolioOptimization:
    """Read + verify the walked optimization recipe (id + pinned hash, fail closed)."""
    try:
        result = store.read_as(optimization_id, PortfolioOptimization.from_dict)
    except (KeyError, ValueError) as exc:
        raise ComparisonConsistencyError(
            f"optimization {optimization_id!r} (referenced by a strategy) could not be "
            "decoded as a PortfolioOptimization (fail closed)"
        ) from exc
    if result is None:
        raise ComparisonConsistencyError(
            f"optimization {optimization_id!r} (referenced by a strategy) is not "
            "present in the research sidecar; cannot reconstruct its date axis (fail "
            "closed)"
        )
    if result.research_result_id != optimization_id:
        raise ComparisonConsistencyError(
            f"optimization {optimization_id!r} resolved to a record whose id "
            f"{result.research_result_id!r} disagrees with the reference (fail closed)"
        )
    if result.result_hash != result_hash:
        raise ComparisonConsistencyError(
            f"optimization {optimization_id!r} has result_hash {result.result_hash!r} "
            f"but the strategy pinned {result_hash!r}; the recipe has drifted since "
            "the walk was sealed (fail closed, SC-1)"
        )
    return result


def _resolve_risk_model(
    store: ResearchResultStore, risk_id: str, result_hash: str
) -> FactorRiskModel:
    """Read + verify the risk model the recipe references (id + pinned hash)."""
    try:
        model = store.read_as(risk_id, FactorRiskModel.from_dict)
    except (KeyError, ValueError) as exc:
        raise ComparisonConsistencyError(
            f"risk model {risk_id!r} (referenced by the optimization) could not be "
            "decoded as a FactorRiskModel (fail closed)"
        ) from exc
    if model is None:
        raise ComparisonConsistencyError(
            f"risk model {risk_id!r} (referenced by the optimization) is not present "
            "in the research sidecar (fail closed)"
        )
    if model.research_result_id != risk_id:
        raise ComparisonConsistencyError(
            f"risk model {risk_id!r} resolved to a record whose id "
            f"{model.research_result_id!r} disagrees with the reference (fail closed)"
        )
    if model.result_hash != result_hash:
        raise ComparisonConsistencyError(
            f"risk model {risk_id!r} has result_hash {model.result_hash!r} but the "
            f"optimization pinned {result_hash!r}; the referenced risk model has "
            "drifted since the recipe was sealed (fail closed, SC-1)"
        )
    return model


def _resolve_factor(
    store: ResearchResultStore, factor_id: str, result_hash: str
) -> FactorPortfolio:
    """Read + verify a referenced factor portfolio (id + pinned hash)."""
    try:
        result = store.read_as(factor_id, FactorPortfolio.from_dict)
    except (KeyError, ValueError) as exc:
        raise ComparisonConsistencyError(
            f"factor portfolio {factor_id!r} could not be decoded as a FactorPortfolio "
            "(fail closed)"
        ) from exc
    if result is None:
        raise ComparisonConsistencyError(
            f"factor portfolio {factor_id!r} is not present in the research sidecar; "
            "cannot reconstruct the date axis (fail closed)"
        )
    if result.research_result_id != factor_id:
        raise ComparisonConsistencyError(
            f"factor portfolio {factor_id!r} resolved to a record whose id "
            f"{result.research_result_id!r} disagrees with the reference (fail closed)"
        )
    if result.result_hash != result_hash:
        raise ComparisonConsistencyError(
            f"factor portfolio {factor_id!r} has result_hash {result.result_hash!r} "
            f"but the risk model pinned {result_hash!r}; the referenced factor has "
            "drifted since the risk model was sealed (fail closed, SC-1)"
        )
    return result


# -- complete-case axis (identical to the walk-forward engine, WF-6) ---------


def _known_dates(factor: FactorPortfolio) -> dict[str, str]:
    """The factor's KNOWN ``as_of -> factor_return`` map (fail closed on dup date).

    Only KNOWN per-period cells contribute (an UNDEFINED period carries no return); a
    duplicate ``as_of`` among the KNOWN cells is a corrupt input (a schedule's dates are
    unique) and raises. The value is retained for parity with the walk-forward engine's
    ``_known_returns`` (only the key set drives the common axis). The reused Phase 20 /
    Phase 22 alignment idiom (WF-6).
    """
    known: dict[str, str] = {}
    for period in factor.per_period:
        cell = period.factor_return
        if cell.status is not FactorPortfolioStatus.KNOWN:
            continue
        assert cell.value is not None  # guaranteed by a KNOWN StatValue
        if period.as_of in known:
            raise ComparisonConsistencyError(
                f"factor {factor.research_result_id!r} carries a duplicate KNOWN "
                f"return for as_of {period.as_of!r}; a schedule's dates must be unique "
                "(fail closed)"
            )
        known[period.as_of] = cell.value
    return known


def _common_dates(known_by_factor: list[dict[str, str]]) -> list[str]:
    """The complete-case common dates, ascending (identical to the walk engine, WF-6).

    The intersection of the ``as_of`` instants where **every** factor carries a KNOWN
    return, sorted ascending (lexicographic over the ISO-like instant strings the
    schedule emits). A date where any factor is UNDEFINED is excluded (complete-case),
    never filled or interpolated.
    """
    if not known_by_factor:
        return []
    common: set[str] = set(known_by_factor[0])
    for known in known_by_factor[1:]:
        common &= known.keys()
    return sorted(common)
