"""The sealed, content-addressed portfolio-optimization record (§14, §13).

A completed optimization is a :class:`PortfolioOptimization`: the engine version, the
full declarative request, the objective and constraint spec, the covariance basis, the
``(factor_risk_id, result_hash)`` reference to the one optimized risk model, the shared
``schedule_id`` and producing ``factor_portfolio_engine_version_id`` (carried from the
risk model), the factor count and ordered labels, the GMV status, the per-factor weight
cells, the achieved per-period portfolio variance and volatility, the carried-through
corpus pins, and the sealed ``result_hash`` over the computed answer.

Like every research record in this project it satisfies the
:class:`~quantforge.factors.store.ResearchRecord` Protocol - ``research_result_id``
aliases ``optimization_id`` (a single id, mirroring ``factor_risk_id``) and ``to_dict``
is deterministic - so it persists write-once to the shared Phase 8 sidecar with **no new
store** (§16). It stores only a *pointer* to the referenced risk model
(``(factor_risk_id, result_hash)``), never a copy of its covariance matrix: the
referenced record already lives in the same sidecar, so this record stays a thin,
reproducible index over it (the pointer-only discipline of the factor-risk / attribution
layers).

**Ex-post, not PIT (PO-2).** The GMV weights are a function of the ex-post
:class:`~quantforge.factorrisk.result.FactorRiskModel` covariance and are themselves
ex-post research statistics, not forward-usable PIT decisions.
:class:`PortfolioOptimization` is deliberately **not** a ``Pit*`` type and exposes
**no** as-of accessor: it can never be handed to a layer that requires a PIT signal.
``boundary_kind = "pit"`` documents only that the *underlying factor portfolios were PIT
walks* - the convention where the label describes the input side, not the ex-post
output. It is not a ``BacktestResult`` and performs no execution (PO-5).

Every value is deterministically serializable and round-trips byte-identically through
:meth:`~PortfolioOptimization.from_dict`; the derived ids are re-emitted by their
properties, never read from stored state, so a tampered stored id is ignored and
``from_dict(to_dict(r))`` re-emits identical bytes. No wall-clock, RNG, or
iteration-order dependence enters any value or id.
"""

from __future__ import annotations

from dataclasses import dataclass

from quantforge.optimization.identity import optimization_id as _optimization_id
from quantforge.optimization.identity import (
    optimization_result_hash as _result_hash,
)
from quantforge.optimization.model import (
    OptimizationStatus,
    StatValue,
    WeightCell,
)
from quantforge.optimization.version import OPTIMIZATION_SOLVE_VERSION

__all__ = [
    "BOUNDARY_PIT",
    "COVARIANCE_BASIS_PER_PERIOD",
    "OPTIMIZATION_RESULT_FORMAT_VERSION",
    "PortfolioOptimization",
]

#: The §14 record-schema version for the optimization record - distinct from the
#: engine-logic version, the solve version, and the sidecar's container format version.
#: Bump it when the serialized meaning of an optimization record changes (a container
#: concern; it is **not** folded into ``optimization_id`` - §13, prior-phase
#: discipline).
OPTIMIZATION_RESULT_FORMAT_VERSION = "optimization-result/1"

#: The only boundary a v1 optimization record accepts (§12, inv. 27/28). The referenced
#: risk model is ex-post over PIT-walked factor portfolios, so this documents the
#: *input* side; the optimization *output* is ex-post and is not a PIT value (PO-2).
#: A REVISED scope is reserved for a future explicitly-labelled phase.
BOUNDARY_PIT = "pit"

#: The covariance basis the solve uses (approved decision, §23). GMV weights are
#: invariant to positive scaling of ``Σ``, so per-period and annualized covariance give
#: identical weights; the per-period covariance is used and the achieved per-period
#: variance is sealed. Folded into ``optimization_id`` so a future annualized-basis
#: option can never collide with this one.
COVARIANCE_BASIS_PER_PERIOD = "per_period"


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


def _as_dict(value: object, key: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"each {key} entry must be an object")
    return value


def _as_str(value: object, key: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"each {key} entry must be a string")
    return value


def _risk_model_ref(raw: dict[str, object]) -> tuple[str, str]:
    """Decode the ``[factor_risk_id, result_hash]`` reference pair (fail closed)."""
    ref = raw.get("risk_model_ref")
    if (
        not isinstance(ref, list)
        or len(ref) != 2
        or not all(isinstance(item, str) for item in ref)
    ):
        raise ValueError(
            "risk_model_ref must be an [factor_risk_id, result_hash] string pair"
        )
    return ref[0], ref[1]


@dataclass(frozen=True, slots=True)
class PortfolioOptimization:
    """A sealed, content-addressed global minimum-variance record (§14).

    Implements the :class:`~quantforge.factors.store.ResearchRecord` Protocol
    (:attr:`research_result_id` aliases :attr:`optimization_id`; deterministic
    :meth:`to_dict`), so it persists write-once to the shared research sidecar with
    no new store. It pins the optimized risk model by ``(factor_risk_id, result_hash)``,
    records the objective / constraint spec / covariance basis, carries the shared
    schedule and producing engine version and the factor count + labels, holds the
    per-factor weight cells and the achieved variance / volatility, carries the
    referenced corpus pins, and seals the computed answer into ``result_hash`` - so
    its identity is a pure function of the request, the referenced content, and the
    computed weights. It is **not** a ``Pit*`` type and exposes no as-of accessor
    (PO-2), and is not a ``BacktestResult`` (PO-5).
    """

    optimization_engine_version_id: str
    optimization_spec: dict[str, object]
    objective: str
    constraint_spec: dict[str, object]
    covariance_basis: str
    risk_model_ref: tuple[str, str]
    boundary_kind: str
    schedule_id: str
    factor_portfolio_engine_version_id: str
    n_factors: int
    factor_labels: tuple[str, ...]
    status: OptimizationStatus
    weights: tuple[WeightCell, ...]
    portfolio_variance: StatValue
    portfolio_volatility: StatValue
    dataset_version_ids: tuple[str, ...]
    market_dataset_version_ids: tuple[str, ...]
    formula_version: str
    result_hash: str

    # -- derived ids (never stored as state) ---------------------------------

    @property
    def optimization_id(self) -> str:
        """The content-addressed id - request, referenced content, **and** answer (§13).

        Re-derived from the record's own fields on every access (never read from stored
        state), so a tampered stored id is ignored and ``from_dict(to_dict(r))``
        re-emits an identical id. Folds the engine version, the spec identity (extracted
        from the embedded request), the objective, the canonical constraint spec, the
        covariance basis, the referenced risk model (id + ``result_hash``), and the
        sealed ``result_hash`` over the computed answer.
        """
        spec = self.optimization_spec
        return _optimization_id(
            optimization_engine_version_id=self.optimization_engine_version_id,
            name=_spec_str(spec, "name"),
            spec_version=_spec_str(spec, "spec_version"),
            objective=self.objective,
            constraint_spec=dict(self.constraint_spec),
            covariance_basis=self.covariance_basis,
            factor_risk_id=self.risk_model_ref[0],
            factor_risk_result_hash=self.risk_model_ref[1],
            result_hash=self.result_hash,
        )

    @property
    def research_result_id(self) -> str:
        """Alias of :attr:`optimization_id` - the :class:`ResearchRecord` identity."""
        return self.optimization_id

    @property
    def factor_risk_id(self) -> str:
        """The referenced (optimized) risk model's id."""
        return self.risk_model_ref[0]

    @property
    def pin_mismatch(self) -> bool:
        """True iff the carried corpus pins are not singular (§14, inherited from FR-3).

        Surfaced, never raised (mirrors ``FactorRiskModel.pin_mismatch``): the
        referenced risk model may legitimately have been estimated over factors run
        on a different corpus snapshot, but a reader must be able to see that the
        carried pins were not singular. Flagged when more than one distinct pin
        appears in either the fundamentals or the market dimension.
        """
        return (
            len(self.dataset_version_ids) > 1
            or len(self.market_dataset_version_ids) > 1
        )

    # -- sealing --------------------------------------------------------------

    @classmethod
    def seal(
        cls,
        *,
        optimization_engine_version_id: str,
        optimization_spec: dict[str, object],
        objective: str,
        constraint_spec: dict[str, object],
        covariance_basis: str,
        risk_model_ref: tuple[str, str],
        boundary_kind: str,
        schedule_id: str,
        factor_portfolio_engine_version_id: str,
        n_factors: int,
        factor_labels: tuple[str, ...],
        status: OptimizationStatus,
        weights: tuple[WeightCell, ...],
        portfolio_variance: StatValue,
        portfolio_volatility: StatValue,
        dataset_version_ids: tuple[str, ...],
        market_dataset_version_ids: tuple[str, ...],
        formula_version: str = OPTIMIZATION_SOLVE_VERSION,
    ) -> PortfolioOptimization:
        """Seal computed blocks, folding the answer into ``result_hash`` (§13).

        The single constructor the engine uses: it folds the ordered computed-output
        cells (the status, then the per-factor weight cells in factor order, then the
        variance and volatility) into ``result_hash`` via
        :func:`~quantforge.optimization.identity.optimization_result_hash`, so
        identity is a pure function of the computed answer and never has to be supplied
        by the caller.
        """
        rhash = _result_hash(
            _output_cells(
                status=status,
                weights=weights,
                portfolio_variance=portfolio_variance,
                portfolio_volatility=portfolio_volatility,
            )
        )
        return cls(
            optimization_engine_version_id=optimization_engine_version_id,
            optimization_spec=dict(optimization_spec),
            objective=objective,
            constraint_spec=dict(constraint_spec),
            covariance_basis=covariance_basis,
            risk_model_ref=risk_model_ref,
            boundary_kind=boundary_kind,
            schedule_id=schedule_id,
            factor_portfolio_engine_version_id=factor_portfolio_engine_version_id,
            n_factors=n_factors,
            factor_labels=factor_labels,
            status=status,
            weights=weights,
            portfolio_variance=portfolio_variance,
            portfolio_volatility=portfolio_volatility,
            dataset_version_ids=dataset_version_ids,
            market_dataset_version_ids=market_dataset_version_ids,
            formula_version=formula_version,
            result_hash=rhash,
        )

    # -- serialization --------------------------------------------------------

    def to_dict(self) -> dict[str, object]:
        return {
            "optimization_id": self.optimization_id,
            # The ResearchRecord alias so the generic sidecar reader keys correctly.
            "research_result_id": self.research_result_id,
            "optimization_engine_version_id": self.optimization_engine_version_id,
            "optimization_spec": dict(self.optimization_spec),
            "objective": self.objective,
            "constraint_spec": dict(self.constraint_spec),
            "covariance_basis": self.covariance_basis,
            "risk_model_ref": [self.risk_model_ref[0], self.risk_model_ref[1]],
            "boundary_kind": self.boundary_kind,
            "schedule_id": self.schedule_id,
            "factor_portfolio_engine_version_id": (
                self.factor_portfolio_engine_version_id
            ),
            "n_factors": self.n_factors,
            "factor_labels": list(self.factor_labels),
            "status": self.status.value,
            "weights": [cell.to_dict() for cell in self.weights],
            "portfolio_variance": self.portfolio_variance.to_dict(),
            "portfolio_volatility": self.portfolio_volatility.to_dict(),
            "dataset_version_ids": list(self.dataset_version_ids),
            "market_dataset_version_ids": list(self.market_dataset_version_ids),
            "formula_version": self.formula_version,
            "result_hash": self.result_hash,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> PortfolioOptimization:
        """Reconstruct a sealed optimization record from its :meth:`to_dict` payload.

        The additive inverse of :meth:`to_dict`, so a record read back from the shared
        sidecar via ``store.read_as(id, PortfolioOptimization.from_dict)`` is a
        first-class typed object. ``optimization_id`` / ``research_result_id`` are
        derived aliases re-emitted by their properties (never read from state), every
        nested cell round-trips through its own fail-closed ``from_dict``, and the
        block order is preserved - so ``from_dict(to_dict(r))`` re-emits identical
        bytes and the same ``result_hash``, introducing no drift.
        """
        status_raw = _req_str(raw, "status")
        try:
            status = OptimizationStatus(status_raw)
        except ValueError as exc:
            raise ValueError(f"unknown optimization status {status_raw!r}") from exc
        return cls(
            optimization_engine_version_id=_req_str(
                raw, "optimization_engine_version_id"
            ),
            optimization_spec=dict(_req_dict(raw, "optimization_spec")),
            objective=_req_str(raw, "objective"),
            constraint_spec=dict(_req_dict(raw, "constraint_spec")),
            covariance_basis=_req_str(raw, "covariance_basis"),
            risk_model_ref=_risk_model_ref(raw),
            boundary_kind=_req_str(raw, "boundary_kind"),
            schedule_id=_req_str(raw, "schedule_id"),
            factor_portfolio_engine_version_id=_req_str(
                raw, "factor_portfolio_engine_version_id"
            ),
            n_factors=_req_int(raw, "n_factors"),
            factor_labels=tuple(
                _as_str(item, "factor_labels")
                for item in _req_list(raw, "factor_labels")
            ),
            status=status,
            weights=tuple(
                WeightCell.from_dict(_as_dict(item, "weights"))
                for item in _req_list(raw, "weights")
            ),
            portfolio_variance=StatValue.from_dict(
                _req_dict(raw, "portfolio_variance")
            ),
            portfolio_volatility=StatValue.from_dict(
                _req_dict(raw, "portfolio_volatility")
            ),
            dataset_version_ids=tuple(
                _as_str(item, "dataset_version_ids")
                for item in _req_list(raw, "dataset_version_ids")
            ),
            market_dataset_version_ids=tuple(
                _as_str(item, "market_dataset_version_ids")
                for item in _req_list(raw, "market_dataset_version_ids")
            ),
            formula_version=_req_str(raw, "formula_version"),
            result_hash=_req_str(raw, "result_hash"),
        )


def _output_cells(
    *,
    status: OptimizationStatus,
    weights: tuple[WeightCell, ...],
    portfolio_variance: StatValue,
    portfolio_volatility: StatValue,
) -> list[dict[str, object]]:
    """The ordered computed-output cells sealed into ``result_hash`` (§13).

    A single deterministic list - the status cell, then the per-factor weight cells in
    factor order, then the variance and volatility cells - each tagged by its block
    so two structurally different records can never collide, and each reduced to its
    canonical form. Sensitive to every computed value: one differing cell changes
    ``result_hash`` and therefore ``optimization_id``. The factor count, labels,
    carried pins, and
    references are deliberately excluded (request / provenance metadata, not the answer;
    they are folded into ``optimization_id`` through the request + reference instead).
    """
    cells: list[dict[str, object]] = [{"block": "status", "status": status.value}]
    for cell in weights:
        cells.append(
            {"block": "weight", "label": cell.label, "value": cell.value.to_dict()}
        )
    cells.append({"block": "variance", "value": portfolio_variance.to_dict()})
    cells.append({"block": "volatility", "value": portfolio_volatility.to_dict()})
    return cells


def _spec_str(spec: dict[str, object], key: str) -> str:
    """Read a required string field from the embedded request payload (fail closed)."""
    value = spec.get(key)
    if not isinstance(value, str):
        raise ValueError(f"optimization_spec.{key} must be a string")
    return value
