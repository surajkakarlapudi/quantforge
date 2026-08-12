"""The sealed, content-addressed walk-forward-evaluation record (§14, §13).

A completed walk-forward evaluation is a :class:`WalkForwardEvaluation`: the engine
version, the full declarative request, the ``(optimization_id, result_hash)`` reference
to the one walked recipe, the shared ``schedule_id`` and producing
``factor_portfolio_engine_version_id`` (carried transitively from the risk model), the
factor count and ordered labels, the inherited annualization + risk-free conventions,
the common-axis period count, the ordered per-window results, the chained out-of-sample
(OOS) return series, the aggregated performance summary, the aggregate realized OOS
variance, the carried-through corpus pins, and the sealed ``result_hash`` over the
computed answer.

Like every research record in this project it satisfies the
:class:`~quantforge.factors.store.ResearchRecord` Protocol - ``research_result_id``
aliases ``walk_forward_id`` (a single id, mirroring ``optimization_id``) and ``to_dict``
is deterministic - so it persists write-once to the shared Phase 8 sidecar with **no new
store**. It stores only a *pointer* to the referenced optimization (``(optimization_id,
result_hash)``), never a copy of its weights or the factors' return series: the
referenced records already live in the same sidecar, so this record stays a thin,
reproducible index over them (the pointer-only discipline of the optimization /
factor-risk layers).

**Ex-post research, not PIT (analogue of PO-2).** An OOS evaluation is an ex-post
research statistic, not a forward-usable PIT decision. :class:`WalkForwardEvaluation` is
deliberately **not** a ``Pit*`` type and exposes **no** as-of accessor; ``boundary_kind
= "pit"`` documents only that the *underlying factor portfolios were PIT walks* - the
convention where the label describes the input side, not the ex-post output. It is not a
``BacktestResult`` and performs no execution.

Every value is deterministically serializable and round-trips byte-identically through
:meth:`~WalkForwardEvaluation.from_dict`; the derived ids are re-emitted by their
properties, never read from stored state, so a tampered stored id is ignored and
``from_dict(to_dict(r))`` re-emits identical bytes. No wall-clock, RNG, or
iteration-order dependence enters any value or id.
"""

from __future__ import annotations

from dataclasses import dataclass

from quantforge.walkforward.identity import walk_forward_id as _walk_forward_id
from quantforge.walkforward.identity import (
    walk_forward_result_hash as _result_hash,
)
from quantforge.walkforward.model import (
    StatValue,
    WalkForwardSummary,
    WalkForwardUndefinedReason,
    WindowStatus,
)
from quantforge.walkforward.version import WALKFORWARD_METHOD_VERSION

__all__ = [
    "BOUNDARY_PIT",
    "MIN_VALID_WINDOWS",
    "WALKFORWARD_RESULT_FORMAT_VERSION",
    "WalkForwardEvaluation",
    "WindowResult",
]

#: The §14 record-schema version for the walk-forward record - distinct from the
#: engine-logic version, the method version, and the sidecar's container format version.
#: Bump it when the serialized meaning of a record changes (a container concern; it is
#: **not** folded into ``walk_forward_id`` - §13, prior-phase discipline).
WALKFORWARD_RESULT_FORMAT_VERSION = "walkforward-result/1"

#: The only boundary a v1 walk-forward record accepts. The referenced optimization is
#: ex-post over PIT-walked factor portfolios, so this documents the *input* side; the
#: evaluation *output* is ex-post and is not a PIT value. A REVISED scope is reserved
#: for a future explicitly-labelled phase.
BOUNDARY_PIT = "pit"

#: The minimum number of REALIZED windows a sealed evaluation must contain (§15, WF-4).
#: A single OOS window carries no cross-window structure and cannot support a defensible
#: OOS summary; below this the engine fails closed rather than seal a degenerate walk.
#: Also the threshold the :attr:`WalkForwardEvaluation.status` roll-up reports against.
MIN_VALID_WINDOWS = 2


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


def _optimization_ref(raw: dict[str, object]) -> tuple[str, str]:
    """Decode the ``[optimization_id, result_hash]`` reference pair (fail closed)."""
    ref = raw.get("optimization_ref")
    if (
        not isinstance(ref, list)
        or len(ref) != 2
        or not all(isinstance(item, str) for item in ref)
    ):
        raise ValueError(
            "optimization_ref must be an [optimization_id, result_hash] string pair"
        )
    return ref[0], ref[1]


@dataclass(frozen=True, slots=True)
class WindowResult:
    """One sealed train->test window (§14, WF-2/WF-4).

    ``[train_start, train_end)`` / ``[test_start, test_end)`` are the half-open axis
    index ranges (``train_end == test_start`` by WF-2). ``status`` is ``REALIZED`` or
    ``UNDEFINED`` (with ``reason``). ``weights`` are the per-factor training GMV weights
    in factor order (KNOWN when REALIZED, empty when UNDEFINED). ``predicted_variance``
    is the in-sample ``wᵀΣw`` over the training covariance; ``realized_variance`` the
    population variance of the OOS test returns. ``oos_returns`` are the realized OOS
    return decimal strings in test-date order (audit metadata: **not** folded into the
    record hash - they are the same numbers as the chained OOS series, which is folded
    once).
    """

    index: int
    train_start: int
    train_end: int
    test_start: int
    test_end: int
    status: WindowStatus
    reason: WalkForwardUndefinedReason | None
    weights: tuple[StatValue, ...]
    predicted_variance: StatValue
    realized_variance: StatValue
    oos_returns: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "index": self.index,
            "train_start": self.train_start,
            "train_end": self.train_end,
            "test_start": self.test_start,
            "test_end": self.test_end,
            "status": self.status.value,
            "weights": [cell.to_dict() for cell in self.weights],
            "predicted_variance": self.predicted_variance.to_dict(),
            "realized_variance": self.realized_variance.to_dict(),
            "oos_returns": list(self.oos_returns),
        }
        if self.reason is not None:
            payload["reason"] = self.reason.value
        return payload

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> WindowResult:
        status_raw = _req_str(raw, "status")
        try:
            status = WindowStatus(status_raw)
        except ValueError as exc:
            raise ValueError(f"unknown window status {status_raw!r}") from exc
        reason_raw = raw.get("reason")
        reason: WalkForwardUndefinedReason | None
        if reason_raw is None:
            reason = None
        elif isinstance(reason_raw, str):
            try:
                reason = WalkForwardUndefinedReason(reason_raw)
            except ValueError as exc:
                raise ValueError(
                    f"unknown WalkForwardUndefinedReason {reason_raw!r}"
                ) from exc
        else:
            raise ValueError("WindowResult.reason must be a string or absent")
        return cls(
            index=_req_int(raw, "index"),
            train_start=_req_int(raw, "train_start"),
            train_end=_req_int(raw, "train_end"),
            test_start=_req_int(raw, "test_start"),
            test_end=_req_int(raw, "test_end"),
            status=status,
            reason=reason,
            weights=tuple(
                StatValue.from_dict(_as_dict(item, "weights"))
                for item in _req_list(raw, "weights")
            ),
            predicted_variance=StatValue.from_dict(
                _req_dict(raw, "predicted_variance")
            ),
            realized_variance=StatValue.from_dict(_req_dict(raw, "realized_variance")),
            oos_returns=tuple(
                _as_str(item, "oos_returns") for item in _req_list(raw, "oos_returns")
            ),
        )


@dataclass(frozen=True, slots=True)
class WalkForwardEvaluation:
    """A sealed, content-addressed walk-forward-evaluation record (§14).

    Implements the :class:`~quantforge.factors.store.ResearchRecord` Protocol
    (:attr:`research_result_id` aliases :attr:`walk_forward_id`; deterministic
    :meth:`to_dict`), so it persists write-once to the shared research sidecar with no
    new store. It pins the walked recipe by ``(optimization_id, result_hash)``, carries
    the shared schedule and producing engine version and the factor count + labels +
    inherited conventions, holds the ordered per-window results, the chained OOS return
    series, the aggregated summary, and the aggregate realized variance, carries the
    referenced corpus pins, and seals the computed answer into ``result_hash`` - so its
    identity is a pure function of the request, the referenced content, and the computed
    walk. It is **not** a ``Pit*`` type and exposes no as-of accessor.
    """

    walk_forward_engine_version_id: str
    walk_forward_spec: dict[str, object]
    optimization_ref: tuple[str, str]
    boundary_kind: str
    schedule_id: str
    factor_portfolio_engine_version_id: str
    n_factors: int
    factor_labels: tuple[str, ...]
    periods_per_year: str
    risk_free_per_period: str
    common_periods: int
    windows: tuple[WindowResult, ...]
    oos_returns: tuple[str, ...]
    summary: WalkForwardSummary
    realized_variance: StatValue
    dataset_version_ids: tuple[str, ...]
    market_dataset_version_ids: tuple[str, ...]
    formula_version: str
    result_hash: str

    # -- derived ids (never stored as state) ---------------------------------

    @property
    def walk_forward_id(self) -> str:
        """The content-addressed id - request, referenced content, **and** answer (§13).

        Re-derived from the record's own fields on every access (never read from stored
        state), so a tampered stored id is ignored and ``from_dict(to_dict(r))``
        re-emits an identical id. Folds the engine version, the spec identity (extracted
        from the embedded request), the canonical training policy, the inherited
        ``schedule_id``, the referenced optimization (id + ``result_hash``), and the
        sealed ``result_hash`` over the computed walk.
        """
        spec = self.walk_forward_spec
        return _walk_forward_id(
            walk_forward_engine_version_id=self.walk_forward_engine_version_id,
            name=_spec_str(spec, "name"),
            spec_version=_spec_str(spec, "spec_version"),
            training_policy=_spec_dict(spec, "training_policy"),
            schedule_id=self.schedule_id,
            optimization_id=self.optimization_ref[0],
            optimization_result_hash=self.optimization_ref[1],
            result_hash=self.result_hash,
        )

    @property
    def research_result_id(self) -> str:
        """Alias of :attr:`walk_forward_id` - the :class:`ResearchRecord` identity."""
        return self.walk_forward_id

    @property
    def optimization_id(self) -> str:
        """The referenced (walked) optimization recipe's id."""
        return self.optimization_ref[0]

    @property
    def status(self) -> WindowStatus:
        """The roll-up status: ``REALIZED`` iff enough windows realized OOS returns.

        ``REALIZED`` when at least :data:`MIN_VALID_WINDOWS` windows are REALIZED, else
        ``UNDEFINED``. A sealed record always rolls up to ``REALIZED`` (the engine fails
        closed below the threshold, WF-4); the property is derived from :attr:`windows`,
        never stored, so it can never disagree with the sealed windows.
        """
        realized = sum(1 for w in self.windows if w.status is WindowStatus.REALIZED)
        return (
            WindowStatus.REALIZED
            if realized >= MIN_VALID_WINDOWS
            else WindowStatus.UNDEFINED
        )

    @property
    def predicted_vs_realized(
        self,
    ) -> tuple[tuple[int, StatValue, StatValue], ...]:
        """Per REALIZED window: ``(index, predicted_variance, realized_variance)``.

        The non-tautological comparison the walk exists to produce - in-sample
        (training) variance vs out-of-sample (realized) variance, window by window.
        UNDEFINED windows (which have no realized returns) are omitted.
        """
        return tuple(
            (w.index, w.predicted_variance, w.realized_variance)
            for w in self.windows
            if w.status is WindowStatus.REALIZED
        )

    @property
    def pin_mismatch(self) -> bool:
        """True iff the carried corpus pins are not singular (inherited from FR-3).

        Surfaced, never raised (mirrors ``PortfolioOptimization.pin_mismatch``): the
        walked chain may legitimately span factors run on different corpus snapshots,
        but a reader must be able to see that the carried pins were not singular.
        Flagged when more than one distinct pin appears in either the fundamentals or
        the market dimension.
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
        walk_forward_engine_version_id: str,
        walk_forward_spec: dict[str, object],
        optimization_ref: tuple[str, str],
        boundary_kind: str,
        schedule_id: str,
        factor_portfolio_engine_version_id: str,
        n_factors: int,
        factor_labels: tuple[str, ...],
        periods_per_year: str,
        risk_free_per_period: str,
        common_periods: int,
        windows: tuple[WindowResult, ...],
        oos_returns: tuple[str, ...],
        summary: WalkForwardSummary,
        realized_variance: StatValue,
        dataset_version_ids: tuple[str, ...],
        market_dataset_version_ids: tuple[str, ...],
        formula_version: str = WALKFORWARD_METHOD_VERSION,
    ) -> WalkForwardEvaluation:
        """Seal computed blocks, folding the answer into ``result_hash`` (§13).

        The single constructor the engine uses: it folds the ordered computed-output
        cells (each window block in schedule order, then the chained OOS return series,
        then the summary block, then the aggregate realized-variance cell) into
        ``result_hash`` via
        :func:`~quantforge.walkforward.identity.walk_forward_result_hash`, so identity
        is a pure function of the computed answer and never has to be supplied by the
        caller.
        """
        rhash = _result_hash(
            _output_cells(
                windows=windows,
                oos_returns=oos_returns,
                summary=summary,
                realized_variance=realized_variance,
            )
        )
        return cls(
            walk_forward_engine_version_id=walk_forward_engine_version_id,
            walk_forward_spec=dict(walk_forward_spec),
            optimization_ref=optimization_ref,
            boundary_kind=boundary_kind,
            schedule_id=schedule_id,
            factor_portfolio_engine_version_id=factor_portfolio_engine_version_id,
            n_factors=n_factors,
            factor_labels=factor_labels,
            periods_per_year=periods_per_year,
            risk_free_per_period=risk_free_per_period,
            common_periods=common_periods,
            windows=windows,
            oos_returns=oos_returns,
            summary=summary,
            realized_variance=realized_variance,
            dataset_version_ids=dataset_version_ids,
            market_dataset_version_ids=market_dataset_version_ids,
            formula_version=formula_version,
            result_hash=rhash,
        )

    # -- serialization --------------------------------------------------------

    def to_dict(self) -> dict[str, object]:
        return {
            "walk_forward_id": self.walk_forward_id,
            # The ResearchRecord alias so the generic sidecar reader keys correctly.
            "research_result_id": self.research_result_id,
            "walk_forward_engine_version_id": self.walk_forward_engine_version_id,
            "walk_forward_spec": dict(self.walk_forward_spec),
            "optimization_ref": [self.optimization_ref[0], self.optimization_ref[1]],
            "boundary_kind": self.boundary_kind,
            "schedule_id": self.schedule_id,
            "factor_portfolio_engine_version_id": (
                self.factor_portfolio_engine_version_id
            ),
            "n_factors": self.n_factors,
            "factor_labels": list(self.factor_labels),
            "periods_per_year": self.periods_per_year,
            "risk_free_per_period": self.risk_free_per_period,
            "common_periods": self.common_periods,
            "windows": [w.to_dict() for w in self.windows],
            "oos_returns": list(self.oos_returns),
            "summary": self.summary.to_dict(),
            "realized_variance": self.realized_variance.to_dict(),
            "dataset_version_ids": list(self.dataset_version_ids),
            "market_dataset_version_ids": list(self.market_dataset_version_ids),
            "formula_version": self.formula_version,
            "result_hash": self.result_hash,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> WalkForwardEvaluation:
        """Reconstruct a sealed walk-forward record from its :meth:`to_dict` payload.

        The additive inverse of :meth:`to_dict`, so a record read back from the shared
        sidecar via ``store.read_as(id, WalkForwardEvaluation.from_dict)`` is a
        first-class typed object. ``walk_forward_id`` / ``research_result_id`` are
        derived aliases re-emitted by their properties (never read from state), every
        nested cell round-trips through its own fail-closed ``from_dict``, and the block
        order is preserved - so ``from_dict(to_dict(r))`` re-emits identical bytes and
        the same ``result_hash``, introducing no drift.
        """
        return cls(
            walk_forward_engine_version_id=_req_str(
                raw, "walk_forward_engine_version_id"
            ),
            walk_forward_spec=dict(_req_dict(raw, "walk_forward_spec")),
            optimization_ref=_optimization_ref(raw),
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
            periods_per_year=_req_str(raw, "periods_per_year"),
            risk_free_per_period=_req_str(raw, "risk_free_per_period"),
            common_periods=_req_int(raw, "common_periods"),
            windows=tuple(
                WindowResult.from_dict(_as_dict(item, "windows"))
                for item in _req_list(raw, "windows")
            ),
            oos_returns=tuple(
                _as_str(item, "oos_returns") for item in _req_list(raw, "oos_returns")
            ),
            summary=WalkForwardSummary.from_dict(_req_dict(raw, "summary")),
            realized_variance=StatValue.from_dict(_req_dict(raw, "realized_variance")),
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
    windows: tuple[WindowResult, ...],
    oos_returns: tuple[str, ...],
    summary: WalkForwardSummary,
    realized_variance: StatValue,
) -> list[dict[str, object]]:
    """The ordered computed-output cells sealed into ``result_hash`` (§13).

    A single deterministic list - each window block in schedule order (index, bounds,
    status, reason when UNDEFINED, weights, predicted / realized variance), then the
    chained OOS return series, then the summary block, then the aggregate
    realized-variance cell - each tagged by its block so two structurally different
    records can never collide, and each reduced to its canonical form. Sensitive to
    every computed value: one differing cell changes ``result_hash`` and therefore
    ``walk_forward_id``. The per-window ``oos_returns`` are deliberately excluded (audit
    metadata - the same numbers as the chained series, folded once); the factor count,
    labels, carried pins, and references are folded into ``walk_forward_id`` through the
    request + reference instead.
    """
    cells: list[dict[str, object]] = []
    for window in windows:
        cell: dict[str, object] = {
            "block": "window",
            "index": window.index,
            "train_start": window.train_start,
            "train_end": window.train_end,
            "test_start": window.test_start,
            "test_end": window.test_end,
            "status": window.status.value,
            "weights": [w.to_dict() for w in window.weights],
            "predicted_variance": window.predicted_variance.to_dict(),
            "realized_variance": window.realized_variance.to_dict(),
        }
        if window.reason is not None:
            cell["reason"] = window.reason.value
        cells.append(cell)
    cells.append({"block": "oos", "returns": list(oos_returns)})
    cells.append({"block": "summary", **summary.to_dict()})
    cells.append({"block": "realized_variance", "value": realized_variance.to_dict()})
    return cells


def _spec_str(spec: dict[str, object], key: str) -> str:
    """Read a required string field from the embedded request payload (fail closed)."""
    value = spec.get(key)
    if not isinstance(value, str):
        raise ValueError(f"walk_forward_spec.{key} must be a string")
    return value


def _spec_dict(spec: dict[str, object], key: str) -> dict[str, object]:
    """Read a required object field from the embedded request payload (fail closed)."""
    value = spec.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"walk_forward_spec.{key} must be an object")
    return value
