"""The factor-risk orchestration engine (§6, §12, FR-1..FR-5).

:class:`FactorRiskEngine` sits strictly **above** Phase 19: it is a pure consumer that
turns a declarative :class:`~quantforge.factorrisk.spec.FactorRiskSpecification` into a
sealed :class:`~quantforge.factorrisk.result.FactorRiskModel` by *resolving* the
already-sealed :class:`~quantforge.factorportfolio.result.FactorPortfolio` records a
request names (an ordered set of *N* factors), *verifying* them, *aligning* their KNOWN
``(as_of, factor_return)`` series on a common complete-case time axis, *estimating* the
second-moment structure (per-factor means and population volatilities, the ``N x N``
population covariance matrix, and the companion correlation matrix) under the pinned
decimal context, and sealing the answer. It introduces no new data-resolution logic, no
new PIT surface, and no new store: the factor portfolios were sealed PIT-correctly by
Phase 19, and the risk model persists write-once to the shared research sidecar (§6,
§13).

The build (§6):

1. **Resolve** each ``factor_portfolio_id`` from the shared sidecar via
   ``store.read_as(id, FactorPortfolio.from_dict)``. A missing id is a consistency
   defect (we refuse to model an artifact we cannot materialize) and raises
   :class:`~quantforge.factorrisk.errors.FactorRiskConsistencyError` (fail closed).
2. **Verify** each resolved record: its ``research_result_id`` equals the requested id
   (a corrupt sidecar whose key disagrees with its content) - each disagreement raises.
   Unlike Phase 17 (which recomputes a backtest's ``result_hash`` from its ledger), a
   ``FactorPortfolio`` exposes no public content->hash recompute; instead each factor's
   sealed ``result_hash`` is **folded into the model's identity** (FR-1), so the model's
   id is transitively sensitive to any change in any referenced factor.
3. **Verify commensurability** (FR-3): every factor must share one exact ``schedule_id``
   and one ``factor_portfolio_engine_version_id`` - strict, fail-closed; a corpus
   ``pin_mismatch`` is *surfaced* on the record, never raised.
4. **Align** (complete-case): the estimation dates are the intersection of the
   ``as_of`` instants where **every** factor carries a KNOWN return; the aligned series
   are those
   dates' returns in shared ascending date order. A window shorter than
   :data:`_MIN_PERIODS` has no dispersion to estimate and raises a configuration defect
   (FR-4).
5. **Estimate** the moments under the pinned decimal context, UNDEFINED-preserving (no
   float, no RNG, no wall-clock); a zero-volatility factor's correlation cells are
   UNDEFINED ``ZERO_VARIANCE``, never a divide-by-zero.
6. **Seal** the computed blocks into a
   :class:`~quantforge.factorrisk.result.FactorRiskModel` (its ``result_hash`` folds the
   answer) and persist it write-once to the same sidecar. Rebuilding an identical
   request is a byte-identical no-op; a differing payload under the same id fails closed
   via the
   store's guard.

The engine holds no mutable per-run state - a build's state lives entirely in local
variables, so one engine can compute many records and two builds of the same spec over
the same immutable sidecar are byte-identical.
"""

from __future__ import annotations

from quantforge.factorportfolio.model import FactorPortfolioStatus
from quantforge.factorportfolio.result import FactorPortfolio
from quantforge.factorrisk.errors import (
    FactorRiskConfigurationError,
    FactorRiskConsistencyError,
)
from quantforge.factorrisk.model import (
    CoverageSummary,
    FactorCoverage,
    factor_label,
)
from quantforge.factorrisk.result import BOUNDARY_PIT, FactorRiskModel
from quantforge.factorrisk.spec import FactorRiskSpecification
from quantforge.factorrisk.stats import estimate_moments
from quantforge.factorrisk.version import FactorRiskEngineVersion
from quantforge.factors.store import ResearchResultStore
from quantforge.workspace import Workspace

__all__ = ["FactorRiskEngine"]

#: The minimum common-window length the estimate requires (§12, FR-4). A population
#: second moment needs at least two observations to carry any dispersion; below this the
#: covariance/correlation is degenerate, so we raise a configuration defect rather than
#: seal a meaningless matrix.
_MIN_PERIODS = 2


class FactorRiskEngine:
    """Resolve, verify, align, estimate, and seal a factor-risk request (§6).

    Constructed from a :class:`~quantforge.workspace.Workspace` (the composition root);
    it reuses the workspace's shared Phase 8 research sidecar - the same store the
    factor-portfolio engine sealed its artifacts to - so a request models exactly the
    factor portfolios already present. The sidecar may be overridden (for tests). The
    engine pins its estimation logic + formula + decimal context via
    :class:`FactorRiskEngineVersion`, and computes every statistic under that version's
    decimal context.
    """

    def __init__(
        self,
        workspace: Workspace,
        *,
        research_store: ResearchResultStore | None = None,
        version: FactorRiskEngineVersion | None = None,
    ) -> None:
        self._workspace = workspace
        self._research_store = research_store
        self._version = version if version is not None else FactorRiskEngineVersion()

    @property
    def factor_risk_engine_version_id(self) -> str:
        """The engine-logic + formula + decimal-context version folded into every id."""
        return self._version.factor_risk_engine_version_id

    @property
    def research_store(self) -> ResearchResultStore:
        """The shared write-once sidecar the model resolves from and persists to."""
        if self._research_store is not None:
            return self._research_store
        store = self._workspace.research_result_store
        assert isinstance(store, ResearchResultStore)
        return store

    def estimate(self, spec: FactorRiskSpecification) -> FactorRiskModel:
        """Resolve, verify, align, estimate, seal, and persist from ``spec`` (§6).

        Deterministic and reproducible: the same spec over the same immutable sidecar
        re-resolves the same factor portfolios, recomputes byte-identical statistics
        under the pinned decimal context, and seals a byte-identical
        :class:`~quantforge.factorrisk.result.FactorRiskModel` on any machine (whose
        sidecar write is an idempotent no-op). Fails closed on any missing/drifted
        reference, incommensurable factor, or too-short common window.
        """
        if not isinstance(spec, FactorRiskSpecification):
            raise FactorRiskConfigurationError(
                "estimate() requires a FactorRiskSpecification"
            )

        store = self.research_store
        context = self._version.decimal_context()

        # -- resolve + verify each referenced factor (request order) ----------
        factors = [
            self._resolve(factor_id, store) for factor_id in spec.factor_portfolio_ids
        ]

        # -- verify commensurability (one schedule, one producing engine; FR-3)
        schedule_id = self._verify_commensurable(spec, factors)
        factor_portfolio_engine_version_id = factors[
            0
        ].factor_portfolio_engine_version_id

        # -- complete-case alignment on the common KNOWN date axis (FR-4) -----
        known_by_factor = [self._known_returns(factor) for factor in factors]
        common_dates = self._common_dates(known_by_factor)
        m = len(common_dates)
        if m < _MIN_PERIODS:
            raise FactorRiskConfigurationError(
                f"the referenced factors share only {m} complete-case common "
                f"estimation "
                f"date(s), but at least {_MIN_PERIODS} are required for a covariance / "
                "correlation estimate; fail closed rather than seal a degenerate matrix"
            )
        series = [[known[as_of] for as_of in common_dates] for known in known_by_factor]

        # -- estimate the second-moment structure (pinned context) -----------
        estimate = estimate_moments(
            series,
            periods_per_year=spec.periods_per_year,
            context=context,
        )

        # -- coverage (audit only; not folded) --------------------------------
        coverage = CoverageSummary(
            per_factor=tuple(
                FactorCoverage(
                    label=factor_label(i),
                    factor_portfolio_id=factors[i].research_result_id,
                    available=len(known_by_factor[i]),
                    used=m,
                )
                for i in range(len(factors))
            ),
            aligned_periods=m,
            dropped_for_alignment=sum(len(known) for known in known_by_factor)
            - len(factors) * m,
        )

        # -- carried-through corpus pins (distinct, sorted; §9, FR-3) ---------
        dataset_pins = _distinct(*(f.dataset_version_id for f in factors))
        market_pins = _distinct(*(f.market_dataset_version_id for f in factors))

        factor_refs = tuple(
            (factor_label(i), factors[i].research_result_id, factors[i].result_hash)
            for i in range(len(factors))
        )

        model = FactorRiskModel.seal(
            factor_risk_engine_version_id=self._version.factor_risk_engine_version_id,
            factor_risk_spec=spec.to_dict(),
            factor_refs=factor_refs,
            boundary_kind=BOUNDARY_PIT,
            schedule_id=schedule_id,
            factor_portfolio_engine_version_id=factor_portfolio_engine_version_id,
            periods=m,
            periods_per_year=spec.periods_per_year,
            factors=estimate.factors,
            covariance=estimate.covariance,
            correlation=estimate.correlation,
            coverage=coverage,
            dataset_version_ids=dataset_pins,
            market_dataset_version_ids=market_pins,
            formula_version=self._version.formula_version,
        )
        # Persist write-once to the shared research sidecar. Idempotent for a
        # byte-identical re-build; a differing payload under the same id raises there.
        store.write(model)
        return model

    # -- resolution & verification -------------------------------------------

    def _resolve(
        self, factor_portfolio_id: str, store: ResearchResultStore
    ) -> FactorPortfolio:
        """Read + verify a referenced factor portfolio from the sidecar (fail closed).

        Verifies two fail-closed consistency guards: the id is present; and the resolved
        record's own ``research_result_id`` equals the requested id (a corrupt sidecar
        whose key disagrees with its content). Unlike Phase 17 there is no independent
        content->hash recompute for a ``FactorPortfolio``; instead the factor's sealed
        ``result_hash`` is folded into the model's identity (FR-1), so any change to a
        referenced factor changes the model's id. The PIT boundary needs no runtime
        check: a :class:`~quantforge.factorportfolio.result.FactorPortfolio` is PIT-only
        by construction (there is no revised variant), so the sealed risk model carries
        the explicit ``boundary_kind = "pit"`` unconditionally, documenting the input
        side; the risk-model output remains ex-post and non-PIT (FR-2).
        """
        result = store.read_as(factor_portfolio_id, FactorPortfolio.from_dict)
        if result is None:
            raise FactorRiskConsistencyError(
                f"factor portfolio {factor_portfolio_id!r} is not present in the "
                "research sidecar; cannot model an artifact that was never sealed "
                "(fail closed)"
            )
        if result.research_result_id != factor_portfolio_id:
            raise FactorRiskConsistencyError(
                f"factor portfolio {factor_portfolio_id!r} resolved to a record whose "
                f"id {result.research_result_id!r} disagrees with the request; the "
                "sidecar is inconsistent (fail closed)"
            )
        return result

    def _verify_commensurable(
        self, spec: FactorRiskSpecification, factors: list[FactorPortfolio]
    ) -> str:
        """Enforce the strict factor comparability contract, return the schedule (FR-3).

        Fail-closed on any of: a factor whose ``schedule_id`` differs from the first
        factor's (the return series do not align on a common rebalance calendar), or a
        factor whose ``factor_portfolio_engine_version_id`` differs (the series were
        produced by different engine logic and are not commensurable - mirrors Phase
        13/15/17). We never silently align mismatched series; a raised error beats a
        wrong covariance. A corpus pin difference is *not* raised here - it is surfaced
        as
        :attr:`~quantforge.factorrisk.result.FactorRiskModel.pin_mismatch`. Returns the
        single shared ``schedule_id``.
        """
        schedule_id = factors[0].schedule_id
        engine_version = factors[0].factor_portfolio_engine_version_id
        for factor_id, factor in zip(spec.factor_portfolio_ids, factors, strict=True):
            if factor.schedule_id != schedule_id:
                raise FactorRiskConsistencyError(
                    f"factor {factor_id!r} uses schedule {factor.schedule_id!r} but "
                    f"the "
                    f"first factor uses {schedule_id!r}; a risk model requires every "
                    "factor return series to align on the same rebalance schedule "
                    "(fail closed)"
                )
            if factor.factor_portfolio_engine_version_id != engine_version:
                raise FactorRiskConsistencyError(
                    f"factor {factor_id!r} was produced by engine version "
                    f"{factor.factor_portfolio_engine_version_id!r} but the first "
                    f"factor "
                    f"by {engine_version!r}; their return series are not commensurable "
                    "(fail closed)"
                )
        return schedule_id

    def _known_returns(self, factor: FactorPortfolio) -> dict[str, str]:
        """The factor's KNOWN ``as_of -> factor_return`` map (fail closed on a dup
        date).

        Only KNOWN per-period cells contribute (an UNDEFINED period carries no return);
        the value is the already-canonical decimal string the factor portfolio sealed. A
        duplicate ``as_of`` among the KNOWN cells is a corrupt input (a schedule's dates
        are unique) and raises rather than being silently overwritten.
        """
        known: dict[str, str] = {}
        for period in factor.per_period:
            cell = period.factor_return
            if cell.status is not FactorPortfolioStatus.KNOWN:
                continue
            assert cell.value is not None  # guaranteed by a KNOWN StatValue
            if period.as_of in known:
                raise FactorRiskConsistencyError(
                    f"factor {factor.research_result_id!r} carries a duplicate KNOWN "
                    f"return for as_of {period.as_of!r}; a schedule's dates must be "
                    "unique (fail closed)"
                )
            known[period.as_of] = cell.value
        return known

    def _common_dates(self, known_by_factor: list[dict[str, str]]) -> list[str]:
        """The complete-case common estimation dates, ascending (§6, FR-4).

        The intersection of the ``as_of`` instants where **every** factor carries a
        KNOWN return, sorted ascending (lexicographic over the ISO-like instant strings
        the
        schedule emits - the deterministic order Phase 19 uses). A date where any factor
        is UNDEFINED is excluded (complete-case), never filled or interpolated.
        """
        if not known_by_factor:
            return []
        common: set[str] = set(known_by_factor[0])
        for known in known_by_factor[1:]:
            common &= known.keys()
        return sorted(common)


def _distinct(*values: str | None) -> tuple[str, ...]:
    """The distinct non-``None`` pins, sorted (§9, FR-3).

    Sorted so the carried pins are order-independent (they are a set of corpus
    snapshots, not a sequence). A single shared pin collapses to one entry; a
    disagreement across
    factors yields more than one, which
    :attr:`~quantforge.factorrisk.result.FactorRiskModel.pin_mismatch` then surfaces.
    """
    seen = {value for value in values if value is not None}
    return tuple(sorted(seen))
