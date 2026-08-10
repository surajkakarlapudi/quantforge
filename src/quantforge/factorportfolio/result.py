"""The sealed, content-addressed factor-portfolio record (§5.5, §5.6).

A completed construction is a :class:`FactorPortfolio`: the engine version, the full
declarative request, the identity-bearing scalars folded into the id (name, spec
version, the signal ``metric_key`` and its ``period_key``, the universe
``specification_id``, the evaluation ``schedule_id``, the forward-horizon trading-day
count, the quantile count, the leg-weighting scheme, and the annualization convention -
``risk_free_per_period`` + ``periods_per_year``), the two carried-through corpus pins,
the two computed blocks - the per-period factor-return panel (schedule order) and the
aggregated performance summary, each an ordered record of UNDEFINED-preserving
:class:`~quantforge.factorportfolio.model.StatValue` cells - a coverage summary, and the
sealed ``result_hash`` over the computed answer.

Like every research record in this project it satisfies the
:class:`~quantforge.factors.store.ResearchRecord` Protocol - ``research_result_id``
aliases ``factor_portfolio_id`` (a single id, mirroring ``analytics_id`` /
``attribution_id`` / ``crosssection_id`` / ``BacktestResult.backtest_id``) and
``to_dict`` is deterministic - so it persists write-once to the shared Phase 8 research
sidecar with **no new store**. It reads the raw corpora and references them by **corpus
pin** (like Phase 16 / Phase 18, unlike Phase 17), so the id stays sensitive to any
corpus change without folding a sealed artifact hash.

**Ex-post, not PIT (P19-2).** A realized *forward*-return long/short factor series is an
ex-post research artifact, not a forward-usable PIT value. :class:`FactorPortfolio` is
deliberately **not** a ``Pit*`` type and exposes **no** as-of accessor: it can never be
handed to a layer that requires a PIT signal, and it is not a ``BacktestResult``
(P19-5). ``boundary_kind = "pit"`` documents only that the *signal side was read
PIT-correctly* via ``panel_across(as_of=T)`` (the Phase 16 SD-2 / Phase 18 XS-2
convention where the label describes the input side, not the ex-post output).

Every value is deterministically serializable and round-trips byte-identically through
:meth:`~FactorPortfolio.from_dict`; the derived ids are re-emitted by their properties,
never read from stored state, so a tampered stored id is ignored and
``from_dict(to_dict(r))`` re-emits identical bytes. No wall-clock, RNG, or
iteration-order dependence enters any value or id.
"""

from __future__ import annotations

from dataclasses import dataclass

from quantforge.factorportfolio.identity import (
    factor_portfolio_id as _factor_portfolio_id,
)
from quantforge.factorportfolio.identity import (
    factor_portfolio_result_hash as _result_hash,
)
from quantforge.factorportfolio.model import (
    CoverageSummary,
    FactorReturnSummary,
    PerPeriodReturn,
)
from quantforge.factorportfolio.version import FACTORPORTFOLIO_FORMULA_VERSION

__all__ = [
    "BOUNDARY_PIT",
    "FACTORPORTFOLIO_RESULT_FORMAT_VERSION",
    "FactorPortfolio",
]

#: The record-schema version for the factor-portfolio record - distinct from the
#: engine-logic version, the formula version, and the sidecar's container-format
#: version. Bump it when the serialized meaning of a record changes (a container
#: concern; it is **not** folded into ``factor_portfolio_id`` - the Phase 14/15/17/18
#: D-discipline).
FACTORPORTFOLIO_RESULT_FORMAT_VERSION = "factorportfolio-result/1"

#: The only boundary a v1 record accepts (§5.6, P19-2). The signal cross-section is
#: read PIT-correctly via ``panel_across(as_of=T)``, so the record carries this
#: explicit, un-defaulted value and the engine sets it unconditionally. It documents the
#: *input* side (the signals were PIT reads); the factor-return *output* is ex-post and
#: is not a PIT value. A REVISED / as-of scope is reserved for a future
#: explicitly-labelled phase.
BOUNDARY_PIT = "pit"


# -- fail-closed decode helpers ----------------------------------------------


def _req_str(raw: dict[str, object], key: str) -> str:
    value = raw[key]
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string")
    return value


def _req_int(raw: dict[str, object], key: str) -> int:
    value = raw[key]
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{key} must be an int")
    return value


def _req_dict(raw: dict[str, object], key: str) -> dict[str, object]:
    value = raw[key]
    if not isinstance(value, dict):
        raise ValueError(f"{key} must be an object")
    return value


def _req_list(raw: dict[str, object], key: str) -> list[object]:
    value = raw[key]
    if not isinstance(value, list):
        raise ValueError(f"{key} must be a list")
    return value


@dataclass(frozen=True, slots=True)
class FactorPortfolio:
    """A sealed, content-addressed factor return series record (§5.5, §5.6).

    Implements the :class:`~quantforge.factors.store.ResearchRecord` Protocol
    (:attr:`research_result_id` aliases :attr:`factor_portfolio_id`; deterministic
    :meth:`to_dict`), so it persists write-once to the shared research sidecar with no
    new store. It carries the identity-bearing request scalars (name, spec version, the
    signal and its ``period_key``, the universe ``specification_id``, the evaluation
    ``schedule_id``, the forward-horizon day count, the quantile count, the
    leg-weighting scheme, and the annualization convention), the two corpus pins, the
    per-period factor-return panel and the aggregated summary, a coverage summary, and
    seals the computed answer into ``result_hash`` - so its identity is a pure function
    of the request, the referenced corpora, and the computed statistics. It is **not** a
    ``Pit*`` type and exposes no as-of accessor (P19-2), and it is not a
    ``BacktestResult`` (P19-5).
    """

    factor_portfolio_engine_version_id: str
    factor_portfolio_spec: dict[str, object]
    name: str
    spec_version: str
    signal: str
    period_key: str
    universe_specification_id: str
    schedule_id: str
    horizon_days: int
    quantiles: int
    weighting: str
    boundary_kind: str
    risk_free_per_period: str
    periods_per_year: str
    dataset_version_id: str
    market_dataset_version_id: str
    per_period: tuple[PerPeriodReturn, ...]
    summary: FactorReturnSummary
    coverage: CoverageSummary
    formula_version: str
    result_hash: str

    # -- derived ids (never stored as state) ---------------------------------

    @property
    def factor_portfolio_id(self) -> str:
        """The content-addressed id - request, corpora **and** answer (§5.4).

        Re-derived from the record's own fields on every access (never read from stored
        state), so a tampered stored id is ignored and ``from_dict(to_dict(r))``
        re-emits an identical id. Folds the engine version, the request identity (name,
        spec version, the signal and its ``period_key``, the universe
        ``specification_id``, the evaluation ``schedule_id``, the horizon day count, the
        quantile count, the leg weighting, and the annualization convention), both
        corpus pins, and the sealed ``result_hash`` over the computed answer.
        """
        return _factor_portfolio_id(
            factor_portfolio_engine_version_id=self.factor_portfolio_engine_version_id,
            name=self.name,
            spec_version=self.spec_version,
            signal=self.signal,
            period_key=self.period_key,
            universe_specification_id=self.universe_specification_id,
            schedule_id=self.schedule_id,
            horizon_days=self.horizon_days,
            quantiles=self.quantiles,
            weighting=self.weighting,
            risk_free_per_period=self.risk_free_per_period,
            periods_per_year=self.periods_per_year,
            dataset_version_id=self.dataset_version_id,
            market_dataset_version_id=self.market_dataset_version_id,
            result_hash=self.result_hash,
        )

    @property
    def research_result_id(self) -> str:
        """Alias of :attr:`factor_portfolio_id` - the :class:`ResearchRecord`
        identity."""
        return self.factor_portfolio_id

    # -- sealing --------------------------------------------------------------

    @classmethod
    def seal(
        cls,
        *,
        factor_portfolio_engine_version_id: str,
        factor_portfolio_spec: dict[str, object],
        name: str,
        spec_version: str,
        signal: str,
        period_key: str,
        universe_specification_id: str,
        schedule_id: str,
        horizon_days: int,
        quantiles: int,
        weighting: str,
        boundary_kind: str,
        risk_free_per_period: str,
        periods_per_year: str,
        dataset_version_id: str,
        market_dataset_version_id: str,
        per_period: tuple[PerPeriodReturn, ...],
        summary: FactorReturnSummary,
        coverage: CoverageSummary,
        formula_version: str = FACTORPORTFOLIO_FORMULA_VERSION,
    ) -> FactorPortfolio:
        """Seal computed blocks, folding the answer into ``result_hash`` (§5.6).

        The single constructor the engine uses: it folds the ordered computed-output
        cells (the per-period factor-return panel in schedule order, then the summary
        block) into ``result_hash`` via
        :func:`~quantforge.factorportfolio.identity.factor_portfolio_result_hash`, so
        identity is a pure function of the computed answer and never has to be supplied
        by the caller. The leg membership and the coverage summary are audit metadata
        and are **not** folded into ``result_hash`` (§5.6); they are fully determined
        by the same inputs, so they never desynchronize.
        """
        rhash = _result_hash(_output_cells(per_period=per_period, summary=summary))
        return cls(
            factor_portfolio_engine_version_id=factor_portfolio_engine_version_id,
            factor_portfolio_spec=dict(factor_portfolio_spec),
            name=name,
            spec_version=spec_version,
            signal=signal,
            period_key=period_key,
            universe_specification_id=universe_specification_id,
            schedule_id=schedule_id,
            horizon_days=horizon_days,
            quantiles=quantiles,
            weighting=weighting,
            boundary_kind=boundary_kind,
            risk_free_per_period=risk_free_per_period,
            periods_per_year=periods_per_year,
            dataset_version_id=dataset_version_id,
            market_dataset_version_id=market_dataset_version_id,
            per_period=per_period,
            summary=summary,
            coverage=coverage,
            formula_version=formula_version,
            result_hash=rhash,
        )

    # -- serialization --------------------------------------------------------

    def to_dict(self) -> dict[str, object]:
        return {
            "factor_portfolio_id": self.factor_portfolio_id,
            # The ResearchRecord alias so the generic sidecar reader keys correctly.
            "research_result_id": self.research_result_id,
            "factor_portfolio_engine_version_id": (
                self.factor_portfolio_engine_version_id
            ),
            "factor_portfolio_spec": dict(self.factor_portfolio_spec),
            "name": self.name,
            "spec_version": self.spec_version,
            "signal": self.signal,
            "period_key": self.period_key,
            "universe_specification_id": self.universe_specification_id,
            "schedule_id": self.schedule_id,
            "horizon_days": self.horizon_days,
            "quantiles": self.quantiles,
            "weighting": self.weighting,
            "boundary_kind": self.boundary_kind,
            "risk_free_per_period": self.risk_free_per_period,
            "periods_per_year": self.periods_per_year,
            "dataset_version_id": self.dataset_version_id,
            "market_dataset_version_id": self.market_dataset_version_id,
            "per_period": [p.to_dict() for p in self.per_period],
            "summary": self.summary.to_dict(),
            "coverage": self.coverage.to_dict(),
            "formula_version": self.formula_version,
            "result_hash": self.result_hash,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> FactorPortfolio:
        """Reconstruct a sealed record from its :meth:`to_dict` payload (fail closed).

        The additive inverse of :meth:`to_dict`, so a record read back from the shared
        sidecar via ``store.read_as(id, FactorPortfolio.from_dict)`` is a first-class
        typed object. ``factor_portfolio_id`` / ``research_result_id`` are derived
        aliases re-emitted by their properties (never read from state), every nested
        record round-trips through its own fail-closed ``from_dict``, and the block
        order is preserved - so ``from_dict(to_dict(r))`` re-emits identical bytes and
        the same ``result_hash``, introducing no drift.
        """
        per_period_raw = _req_list(raw, "per_period")
        per_period = tuple(
            PerPeriodReturn.from_dict(item)
            for item in per_period_raw
            if isinstance(item, dict)
        )
        if len(per_period) != len(per_period_raw):
            raise ValueError("each per_period entry must be an object")
        return cls(
            factor_portfolio_engine_version_id=_req_str(
                raw, "factor_portfolio_engine_version_id"
            ),
            factor_portfolio_spec=dict(_req_dict(raw, "factor_portfolio_spec")),
            name=_req_str(raw, "name"),
            spec_version=_req_str(raw, "spec_version"),
            signal=_req_str(raw, "signal"),
            period_key=_req_str(raw, "period_key"),
            universe_specification_id=_req_str(raw, "universe_specification_id"),
            schedule_id=_req_str(raw, "schedule_id"),
            horizon_days=_req_int(raw, "horizon_days"),
            quantiles=_req_int(raw, "quantiles"),
            weighting=_req_str(raw, "weighting"),
            boundary_kind=_req_str(raw, "boundary_kind"),
            risk_free_per_period=_req_str(raw, "risk_free_per_period"),
            periods_per_year=_req_str(raw, "periods_per_year"),
            dataset_version_id=_req_str(raw, "dataset_version_id"),
            market_dataset_version_id=_req_str(raw, "market_dataset_version_id"),
            per_period=per_period,
            summary=FactorReturnSummary.from_dict(_req_dict(raw, "summary")),
            coverage=CoverageSummary.from_dict(_req_dict(raw, "coverage")),
            formula_version=_req_str(raw, "formula_version"),
            result_hash=_req_str(raw, "result_hash"),
        )


def _output_cells(
    *,
    per_period: tuple[PerPeriodReturn, ...],
    summary: FactorReturnSummary,
) -> list[dict[str, object]]:
    """The ordered computed-output cells sealed into ``result_hash`` (§5.6).

    A single deterministic list - the per-period factor-return panel in schedule order
    (each period reduced to its ``as_of``, ``n_members``, and the three leg/spread
    cells), then the aggregated summary block - each cell tagged by its block so two
    structurally different records can never collide, and each reduced to its canonical
    form. Sensitive to every computed statistic (each period's member count, long-leg
    mean, short-leg mean, and factor return, and every summary cell): one differing cell
    changes ``result_hash`` and therefore ``factor_portfolio_id``. The per-period **leg
    membership** and the **coverage summary** are deliberately excluded (§5.6) - they
    are audit metadata, fully determined by the same inputs.
    """
    cells: list[dict[str, object]] = []
    for period in per_period:
        cells.append(
            {
                "block": "per_period",
                "as_of": period.as_of,
                "n_members": period.n_members,
                "long_return": period.long_return.to_dict(),
                "short_return": period.short_return.to_dict(),
                "factor_return": period.factor_return.to_dict(),
            }
        )
    cells.append({"block": "summary", **summary.to_dict()})
    return cells
