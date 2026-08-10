"""The sealed, content-addressed cross-sectional-regression record (§3.2, §5).

A completed Fama-MacBeth estimation is a :class:`CrossSectionalRegression`: the engine
version, the full declarative request, the identity-bearing scalars folded into the id
(name, spec version, the **ordered** factor descriptors, the universe
``specification_id``, the evaluation ``schedule_id``, the forward-horizon trading-day
count, and the intercept flag), the two carried-through corpus pins, the two computed
blocks - the per-date coefficient panel (schedule order) and the aggregated factor
premia (factor order), each an ordered record of UNDEFINED-preserving
:class:`~quantforge.crosssection.model.StatValue` cells - a coverage summary, and the
sealed ``result_hash`` over the computed answer.

Like every research record in this project it satisfies the
:class:`~quantforge.factors.store.ResearchRecord` Protocol - ``research_result_id``
aliases ``crosssection_id`` (a single id, mirroring ``analytics_id`` /
``attribution_id`` / ``BacktestResult.backtest_id``) and ``to_dict`` is deterministic -
so it persists write-once to the shared Phase 8 research sidecar with **no new store**.
It reads the raw corpora and references them by **corpus pin** (like Phase 16, unlike
Phase 17), so the id stays sensitive to any corpus change without folding a sealed
artifact hash.

**Ex-post, not PIT (XS-2).** A regression of realized *forward* returns on as-of-``T``
signals is an ex-post research statistic, not a forward-usable PIT value.
:class:`CrossSectionalRegression` is deliberately **not** a ``Pit*`` type and exposes
**no** as-of accessor: it can never be handed to a layer that requires a PIT signal.
``boundary_kind = "pit"`` documents only that the *signal side was read PIT-correctly*
via ``panel_across(as_of=T)`` (the Phase 16 SD-2 convention where the label describes
the input side, not the ex-post output).

Every value is deterministically serializable and round-trips byte-identically through
:meth:`~CrossSectionalRegression.from_dict`; the derived ids are re-emitted by their
properties, never read from stored state, so a tampered stored id is ignored and
``from_dict(to_dict(r))`` re-emits identical bytes. No wall-clock, RNG, or
iteration-order dependence enters any value or id.
"""

from __future__ import annotations

from dataclasses import dataclass

from quantforge.crosssection.identity import crosssection_id as _crosssection_id
from quantforge.crosssection.identity import (
    crosssection_result_hash as _result_hash,
)
from quantforge.crosssection.model import (
    CoverageSummary,
    PerDateCoefficients,
    PremiumEstimate,
)
from quantforge.crosssection.version import CROSSSECTION_FORMULA_VERSION

__all__ = [
    "BOUNDARY_PIT",
    "CROSSSECTION_RESULT_FORMAT_VERSION",
    "CrossSectionalRegression",
]

#: The record-schema version for the cross-sectional-regression record - distinct from
#: the engine-logic version, the formula version, and the sidecar's container-format
#: version. Bump it when the serialized meaning of a record changes (a container
#: concern; it is **not** folded into ``crosssection_id`` - the Phase 14/15/17
#: D-discipline).
CROSSSECTION_RESULT_FORMAT_VERSION = "crosssection-result/1"

#: The only boundary a v1 record accepts (§7, XS-2). The signal cross-section is read
#: PIT-correctly via ``panel_across(as_of=T)``, so the record carries this explicit,
#: un-defaulted value and the engine sets it unconditionally. It documents the *input*
#: side (the signals were PIT reads); the regression *output* is ex-post and is not a
#: PIT value. A REVISED / as-of scope is reserved for a future explicitly-labelled
#: phase.
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


def _req_bool(raw: dict[str, object], key: str) -> bool:
    value = raw[key]
    if not isinstance(value, bool):
        raise ValueError(f"{key} must be a bool")
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


def _factor_descriptors(items: list[object]) -> tuple[tuple[str, str], ...]:
    """Decode the ordered ``[[metric_key, period_key], ...]`` descriptor pairs."""
    out: list[tuple[str, str]] = []
    for item in items:
        if (
            not isinstance(item, list)
            or len(item) != 2
            or not all(isinstance(part, str) for part in item)
        ):
            raise ValueError(
                "each factor descriptor must be a [metric_key, period_key] string pair"
            )
        out.append((item[0], item[1]))
    return tuple(out)


@dataclass(frozen=True, slots=True)
class CrossSectionalRegression:
    """A sealed, content-addressed Fama-MacBeth regression record (§3.2, §5).

    Implements the :class:`~quantforge.factors.store.ResearchRecord` Protocol
    (:attr:`research_result_id` aliases :attr:`crosssection_id`; deterministic
    :meth:`to_dict`), so it persists write-once to the shared research sidecar with no
    new store. It carries the identity-bearing request scalars (name, spec version, the
    ordered factor descriptors, the universe ``specification_id``, the evaluation
    ``schedule_id``, the forward-horizon day count, the intercept flag), the two corpus
    pins, the per-date coefficient panel and the aggregated premia, a coverage summary,
    and seals the computed answer into ``result_hash`` - so its identity is a pure
    function of the request, the referenced corpora, and the computed statistics. It is
    **not** a ``Pit*`` type and exposes no as-of accessor (XS-2).
    """

    crosssection_engine_version_id: str
    crosssection_spec: dict[str, object]
    name: str
    spec_version: str
    factor_descriptors: tuple[tuple[str, str], ...]
    universe_specification_id: str
    schedule_id: str
    horizon_days: int
    include_intercept: bool
    boundary_kind: str
    dataset_version_id: str
    market_dataset_version_id: str
    per_date: tuple[PerDateCoefficients, ...]
    premia: tuple[PremiumEstimate, ...]
    coverage: CoverageSummary
    formula_version: str
    result_hash: str

    # -- derived ids (never stored as state) ---------------------------------

    @property
    def crosssection_id(self) -> str:
        """The content-addressed id - request, corpora **and** answer (§5).

        Re-derived from the record's own fields on every access (never read from stored
        state), so a tampered stored id is ignored and ``from_dict(to_dict(r))``
        re-emits an identical id. Folds the engine version, the request identity (name,
        spec version, the **ordered** factor descriptors, the universe
        ``specification_id``, the evaluation ``schedule_id``, the horizon day count and
        intercept flag), both corpus pins, and the sealed ``result_hash`` over the
        computed answer.
        """
        return _crosssection_id(
            crosssection_engine_version_id=self.crosssection_engine_version_id,
            name=self.name,
            spec_version=self.spec_version,
            factor_descriptors=[list(pair) for pair in self.factor_descriptors],
            universe_specification_id=self.universe_specification_id,
            schedule_id=self.schedule_id,
            horizon_days=self.horizon_days,
            include_intercept=self.include_intercept,
            dataset_version_id=self.dataset_version_id,
            market_dataset_version_id=self.market_dataset_version_id,
            result_hash=self.result_hash,
        )

    @property
    def research_result_id(self) -> str:
        """Alias of :attr:`crosssection_id` - the :class:`ResearchRecord` identity."""
        return self.crosssection_id

    # -- sealing --------------------------------------------------------------

    @classmethod
    def seal(
        cls,
        *,
        crosssection_engine_version_id: str,
        crosssection_spec: dict[str, object],
        name: str,
        spec_version: str,
        factor_descriptors: tuple[tuple[str, str], ...],
        universe_specification_id: str,
        schedule_id: str,
        horizon_days: int,
        include_intercept: bool,
        boundary_kind: str,
        dataset_version_id: str,
        market_dataset_version_id: str,
        per_date: tuple[PerDateCoefficients, ...],
        premia: tuple[PremiumEstimate, ...],
        coverage: CoverageSummary,
        formula_version: str = CROSSSECTION_FORMULA_VERSION,
    ) -> CrossSectionalRegression:
        """Seal computed blocks, folding the answer into ``result_hash`` (§5).

        The single constructor the engine uses: it folds the ordered computed-output
        cells (the per-date coefficient panel in schedule order, then the premia block
        in factor order) into ``result_hash`` via
        :func:`~quantforge.crosssection.identity.crosssection_result_hash`, so identity
        is a pure function of the computed answer and never has to be supplied by the
        caller. The coverage summary is audit metadata and is **not** folded into
        ``result_hash`` (§5); it is fully determined by the same inputs, so it never
        desynchronizes.
        """
        rhash = _result_hash(_output_cells(per_date=per_date, premia=premia))
        return cls(
            crosssection_engine_version_id=crosssection_engine_version_id,
            crosssection_spec=dict(crosssection_spec),
            name=name,
            spec_version=spec_version,
            factor_descriptors=factor_descriptors,
            universe_specification_id=universe_specification_id,
            schedule_id=schedule_id,
            horizon_days=horizon_days,
            include_intercept=include_intercept,
            boundary_kind=boundary_kind,
            dataset_version_id=dataset_version_id,
            market_dataset_version_id=market_dataset_version_id,
            per_date=per_date,
            premia=premia,
            coverage=coverage,
            formula_version=formula_version,
            result_hash=rhash,
        )

    # -- serialization --------------------------------------------------------

    def to_dict(self) -> dict[str, object]:
        return {
            "crosssection_id": self.crosssection_id,
            # The ResearchRecord alias so the generic sidecar reader keys correctly.
            "research_result_id": self.research_result_id,
            "crosssection_engine_version_id": self.crosssection_engine_version_id,
            "crosssection_spec": dict(self.crosssection_spec),
            "name": self.name,
            "spec_version": self.spec_version,
            "factor_descriptors": [list(pair) for pair in self.factor_descriptors],
            "universe_specification_id": self.universe_specification_id,
            "schedule_id": self.schedule_id,
            "horizon_days": self.horizon_days,
            "include_intercept": self.include_intercept,
            "boundary_kind": self.boundary_kind,
            "dataset_version_id": self.dataset_version_id,
            "market_dataset_version_id": self.market_dataset_version_id,
            "per_date": [d.to_dict() for d in self.per_date],
            "premia": [p.to_dict() for p in self.premia],
            "coverage": self.coverage.to_dict(),
            "formula_version": self.formula_version,
            "result_hash": self.result_hash,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> CrossSectionalRegression:
        """Reconstruct a sealed record from its :meth:`to_dict` payload (fail closed).

        The additive inverse of :meth:`to_dict`, so a record read back from the shared
        sidecar via ``store.read_as(id, CrossSectionalRegression.from_dict)`` is a
        first-class typed object. ``crosssection_id`` / ``research_result_id`` are
        derived aliases re-emitted by their properties (never read from state), every
        nested record round-trips through its own fail-closed ``from_dict``, and the
        block order is preserved - so ``from_dict(to_dict(r))`` re-emits identical bytes
        and the same ``result_hash``, introducing no drift.
        """
        per_date_raw = _req_list(raw, "per_date")
        premia_raw = _req_list(raw, "premia")
        per_date = tuple(
            PerDateCoefficients.from_dict(item)
            for item in per_date_raw
            if isinstance(item, dict)
        )
        if len(per_date) != len(per_date_raw):
            raise ValueError("each per_date entry must be an object")
        premia = tuple(
            PremiumEstimate.from_dict(item)
            for item in premia_raw
            if isinstance(item, dict)
        )
        if len(premia) != len(premia_raw):
            raise ValueError("each premia entry must be an object")
        return cls(
            crosssection_engine_version_id=_req_str(
                raw, "crosssection_engine_version_id"
            ),
            crosssection_spec=dict(_req_dict(raw, "crosssection_spec")),
            name=_req_str(raw, "name"),
            spec_version=_req_str(raw, "spec_version"),
            factor_descriptors=_factor_descriptors(
                _req_list(raw, "factor_descriptors")
            ),
            universe_specification_id=_req_str(raw, "universe_specification_id"),
            schedule_id=_req_str(raw, "schedule_id"),
            horizon_days=_req_int(raw, "horizon_days"),
            include_intercept=_req_bool(raw, "include_intercept"),
            boundary_kind=_req_str(raw, "boundary_kind"),
            dataset_version_id=_req_str(raw, "dataset_version_id"),
            market_dataset_version_id=_req_str(raw, "market_dataset_version_id"),
            per_date=per_date,
            premia=premia,
            coverage=CoverageSummary.from_dict(_req_dict(raw, "coverage")),
            formula_version=_req_str(raw, "formula_version"),
            result_hash=_req_str(raw, "result_hash"),
        )


def _output_cells(
    *,
    per_date: tuple[PerDateCoefficients, ...],
    premia: tuple[PremiumEstimate, ...],
) -> list[dict[str, object]]:
    """The ordered computed-output cells sealed into ``result_hash`` (§5).

    A single deterministic list - the per-date coefficient panel in schedule order,
    then the aggregated premia in factor order - each cell tagged by its block so two
    structurally different records can never collide, and each reduced to its canonical
    form. Sensitive to every computed statistic (per-date coefficient, per-date R², and
    every premium's mean / standard error / t-statistic): one differing cell changes
    ``result_hash`` and therefore ``crosssection_id``. The coverage summary is
    deliberately excluded (§5) - it is audit metadata, fully determined by the same
    inputs.
    """
    cells: list[dict[str, object]] = []
    for date_block in per_date:
        cells.append({"block": "per_date", **date_block.to_dict()})
    for premium in premia:
        cells.append({"block": "premium", **premium.to_dict()})
    return cells
