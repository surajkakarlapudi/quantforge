"""The sealed, content-addressed net-of-cost record (§9, §10).

A completed analysis is a :class:`NetOfCostPerformance`: the engine version, the full
declarative request, the ``(source_stability_id, source_result_hash)`` reference to the
one sealed :class:`~quantforge.stability.result.WalkForwardStability` it consumed, the
inherited annualization + risk-free conventions (carried from the walk-forward beneath
the stability record so the net Sharpe matches the gross convention), per **realized**
window the gross / turnover / cost / net aggregate (in the source's window order), the
**excluded** windows (each a window the source sealed UNDEFINED, with its reason), the
aggregate net-of-cost :class:`NetOfCostSummary` (the gross moments carried verbatim, the
net moments, the cost drag, and the parameter-free break-even cost rate), a non-hashed
coverage block, and the sealed ``result_hash`` over the computed answer.

Like every research record in this project it satisfies the
:class:`~quantforge.factors.store.ResearchRecord` Protocol - ``research_result_id``
aliases ``net_of_cost_id`` (a single id, mirroring ``walk_forward_stability_id``) and
``to_dict`` is deterministic - so it persists write-once to the shared Phase 8 sidecar
with **no new store**. It stores only a *pointer* to the source stability record, never
a copy of its windows or the gross return series (the pointer-only discipline of
:class:`~quantforge.calsig.result.CalibrationSignificance`): the source already lives in
the same sidecar, so this record stays a thin, reproducible view over it.

**Ex-post, not PIT (NC-6).** A net-of-cost analysis over an already-ex-post walk-forward
is itself an ex-post research statistic - and, moreover, a **counterfactual**: the net
returns are what the strategy *would* have earned under a *declared* cost model, never a
realized cash flow and never substitutable for the realized (gross) returns.
:class:`NetOfCostPerformance` is deliberately **not** a ``Pit*`` type and exposes **no**
as-of accessor. ``boundary_kind = "pit"`` documents only that the *underlying factor
portfolios* were PIT walks - the convention where the label describes the input side,
not the ex-post output. It is not a ``BacktestResult`` and performs no execution.

Every value is deterministically serializable and round-trips byte-identically through
:meth:`~NetOfCostPerformance.from_dict`; the derived ids are re-emitted by their
properties, never read from stored state. No wall-clock, RNG, or iteration-order
dependence enters any value or id.
"""

from __future__ import annotations

from dataclasses import dataclass

from quantforge.netcost.identity import net_of_cost_id as _netcost_id
from quantforge.netcost.identity import net_of_cost_result_hash as _result_hash
from quantforge.netcost.model import (
    NetCostExcludedReason,
    NetCostStat,
    NetCostStatus,
    NetCostUndefinedReason,
)
from quantforge.netcost.version import NETCOST_METHOD_VERSION

__all__ = [
    "BOUNDARY_PIT",
    "NETCOST_RESULT_FORMAT_VERSION",
    "ExcludedWindow",
    "NetOfCostCoverage",
    "NetOfCostPerformance",
    "NetOfCostSummary",
    "WindowNetCostCell",
]

#: The §9 record-schema version for the net-of-cost record - distinct from the
#: engine-logic version, the method version, and the sidecar's container format version.
#: Bump it when the serialized meaning of a record changes (a container concern; it is
#: **not** folded into ``net_of_cost_id`` - §10, prior-phase discipline).
NETCOST_RESULT_FORMAT_VERSION = "netcost-result/1"

#: The only boundary a v1 net-of-cost record accepts. It documents that the *underlying
#: factor portfolios* (beneath the source walk-forward) were PIT walks; the net-of-cost
#: *output* is ex-post and counterfactual and is not a PIT value (NC-6). The engine
#: carries the source stability record's ``boundary_kind`` through unchanged.
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


def _as_dict(value: object, key: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"each {key} entry must be an object")
    return value


def _cell(raw: dict[str, object], key: str) -> NetCostStat:
    value = raw.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"{key} must be an object")
    return NetCostStat.from_dict(value)


def _excluded_reason(raw: dict[str, object]) -> NetCostExcludedReason:
    """Decode a required exclusion ``reason`` string (fail closed)."""
    reason_raw = raw.get("reason")
    if not isinstance(reason_raw, str):
        raise ValueError("ExcludedWindow.reason must be a string")
    try:
        return NetCostExcludedReason(reason_raw)
    except ValueError as exc:
        raise ValueError(f"unknown NetCostExcludedReason {reason_raw!r}") from exc


@dataclass(frozen=True, slots=True)
class WindowNetCostCell:
    """One realized window's gross / turnover / cost / net aggregate (§9, NC-2).

    ``index`` is the source window's index; ``n_periods`` its OOS-period count;
    ``gross_return`` the additive aggregate ``Σ`` of the window's per-period gross
    returns; ``turnover`` and ``cost`` are UNDEFINED-preserving
    :class:`~quantforge.netcost.model.NetCostStat` cells (both
    ``NO_PRIOR_REALIZED_WINDOW`` when the window has no adjacent realized predecessor -
    zero cost, no fabricated entry cost); ``net_return`` the additive aggregate of the
    window's per-period net returns.
    """

    index: int
    n_periods: int
    gross_return: str
    turnover: NetCostStat
    cost: NetCostStat
    net_return: str

    def to_dict(self) -> dict[str, object]:
        return {
            "index": self.index,
            "n_periods": self.n_periods,
            "gross_return": self.gross_return,
            "turnover": self.turnover.to_dict(),
            "cost": self.cost.to_dict(),
            "net_return": self.net_return,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> WindowNetCostCell:
        return cls(
            index=_req_int(raw, "index"),
            n_periods=_req_int(raw, "n_periods"),
            gross_return=_req_str(raw, "gross_return"),
            turnover=_cell(raw, "turnover"),
            cost=_cell(raw, "cost"),
            net_return=_req_str(raw, "net_return"),
        )


@dataclass(frozen=True, slots=True)
class ExcludedWindow:
    """One window excluded from the net-of-cost family, with its reason (§9, NC-5).

    A window the source stability record excluded (``WINDOW_UNDEFINED``): the walk
    sealed it UNDEFINED, so it carries no gross returns and no turnover. It is recorded
    here,
    never imputed and never charged a cost (NC-5). Carried through verbatim from the
    stability record's excluded set.
    """

    index: int
    reason: NetCostExcludedReason

    def to_dict(self) -> dict[str, object]:
        return {"index": self.index, "reason": self.reason.value}

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> ExcludedWindow:
        return cls(index=_req_int(raw, "index"), reason=_excluded_reason(raw))


@dataclass(frozen=True, slots=True)
class NetOfCostSummary:
    """The aggregate net-of-cost statistics + the roll-up status (§9).

    The gross moments (``gross_mean`` / ``gross_volatility`` / ``gross_sharpe``) are the
    source walk's KNOWN moments carried verbatim (NC-4); the net moments (``net_mean``
    / ``net_volatility`` / ``net_sharpe``) are computed over the net series with the
    reused Phase 19 summary; ``cost_drag_mean`` / ``sharpe_drag`` are the
    gross-minus-net drags;
    ``break_even_cost_rate`` is the parameter-free ``Σ gross / Σ turnover`` (UNDEFINED
    ``DEGENERATE_NO_TURNOVER`` when the strategy never trades); ``total_gross_return`` /
    ``total_turnover`` / ``total_cost`` are the KNOWN additive aggregates; and
    ``net_status`` (``MEASURED`` when the net Sharpe is KNOWN, else ``UNDEFINED`` with
    ``status_reason``). Every moment cell is UNDEFINED-preserving
    :class:`~quantforge.netcost.model.NetCostStat`.
    """

    gross_mean: NetCostStat
    gross_volatility: NetCostStat
    gross_sharpe: NetCostStat
    net_mean: NetCostStat
    net_volatility: NetCostStat
    net_sharpe: NetCostStat
    cost_drag_mean: NetCostStat
    sharpe_drag: NetCostStat
    break_even_cost_rate: NetCostStat
    total_gross_return: str
    total_turnover: str
    total_cost: str
    net_status: NetCostStatus
    status_reason: NetCostUndefinedReason | None = None

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "gross_mean": self.gross_mean.to_dict(),
            "gross_volatility": self.gross_volatility.to_dict(),
            "gross_sharpe": self.gross_sharpe.to_dict(),
            "net_mean": self.net_mean.to_dict(),
            "net_volatility": self.net_volatility.to_dict(),
            "net_sharpe": self.net_sharpe.to_dict(),
            "cost_drag_mean": self.cost_drag_mean.to_dict(),
            "sharpe_drag": self.sharpe_drag.to_dict(),
            "break_even_cost_rate": self.break_even_cost_rate.to_dict(),
            "total_gross_return": self.total_gross_return,
            "total_turnover": self.total_turnover,
            "total_cost": self.total_cost,
            "net_status": self.net_status.value,
        }
        if self.status_reason is not None:
            payload["status_reason"] = self.status_reason.value
        return payload

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> NetOfCostSummary:
        status_raw = _req_str(raw, "net_status")
        try:
            status = NetCostStatus(status_raw)
        except ValueError as exc:
            raise ValueError(f"unknown net_status {status_raw!r}") from exc
        reason_raw = raw.get("status_reason")
        reason: NetCostUndefinedReason | None
        if reason_raw is None:
            reason = None
        elif isinstance(reason_raw, str):
            try:
                reason = NetCostUndefinedReason(reason_raw)
            except ValueError as exc:
                raise ValueError(
                    f"unknown NetCostUndefinedReason {reason_raw!r}"
                ) from exc
        else:
            raise ValueError(
                "NetOfCostSummary.status_reason must be a string or absent"
            )
        return cls(
            gross_mean=_cell(raw, "gross_mean"),
            gross_volatility=_cell(raw, "gross_volatility"),
            gross_sharpe=_cell(raw, "gross_sharpe"),
            net_mean=_cell(raw, "net_mean"),
            net_volatility=_cell(raw, "net_volatility"),
            net_sharpe=_cell(raw, "net_sharpe"),
            cost_drag_mean=_cell(raw, "cost_drag_mean"),
            sharpe_drag=_cell(raw, "sharpe_drag"),
            break_even_cost_rate=_cell(raw, "break_even_cost_rate"),
            total_gross_return=_req_str(raw, "total_gross_return"),
            total_turnover=_req_str(raw, "total_turnover"),
            total_cost=_req_str(raw, "total_cost"),
            net_status=status,
            status_reason=reason,
        )


@dataclass(frozen=True, slots=True)
class NetOfCostCoverage:
    """The audit coverage block - counts of windows, realized, excluded, charged,
    periods (§9).

    A pure function of the sealed window / excluded lists (a reader's convenience, its
    counts folded into ``result_hash`` via the descriptor): the source held
    ``n_windows`` windows, of which ``n_realized`` yielded a net-cost cell and
    ``n_excluded`` were excluded (``n_realized + n_excluded == n_windows``);
    ``n_charged`` is the count of realized windows that bore a KNOWN turnover cost (a
    realized-adjacent predecessor); ``n_periods`` is the total OOS-period count across
    the realized windows (the length of the net series).
    """

    n_windows: int
    n_realized: int
    n_excluded: int
    n_charged: int
    n_periods: int

    def to_dict(self) -> dict[str, object]:
        return {
            "n_windows": self.n_windows,
            "n_realized": self.n_realized,
            "n_excluded": self.n_excluded,
            "n_charged": self.n_charged,
            "n_periods": self.n_periods,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> NetOfCostCoverage:
        return cls(
            n_windows=_req_int(raw, "n_windows"),
            n_realized=_req_int(raw, "n_realized"),
            n_excluded=_req_int(raw, "n_excluded"),
            n_charged=_req_int(raw, "n_charged"),
            n_periods=_req_int(raw, "n_periods"),
        )


@dataclass(frozen=True, slots=True)
class NetOfCostPerformance:
    """A sealed, content-addressed net-of-cost record (§9).

    Implements the :class:`~quantforge.factors.store.ResearchRecord` Protocol
    (:attr:`research_result_id` aliases :attr:`net_of_cost_id`; deterministic
    :meth:`to_dict`), so it persists write-once to the shared research sidecar with no
    new store. It pins the source stability record by ``(id, result_hash)``, carries the
    inherited annualization conventions, holds the per-realized-window net-cost cells,
    the excluded windows, the aggregate summary, and the coverage block, and seals the
    computed answer into ``result_hash``. It is **not** a ``Pit*`` type and exposes no
    as-of accessor (NC-6).
    """

    net_of_cost_engine_version_id: str
    net_of_cost_spec: dict[str, object]
    source_ref: tuple[str, str]
    boundary_kind: str
    periods_per_year: str
    risk_free_per_period: str
    windows: tuple[WindowNetCostCell, ...]
    excluded: tuple[ExcludedWindow, ...]
    summary: NetOfCostSummary
    coverage: NetOfCostCoverage
    method_version: str
    result_hash: str

    # -- derived ids (never stored as state) ---------------------------------

    @property
    def net_of_cost_id(self) -> str:
        """The content-addressed id - request, referenced content, **and** answer (§10).

        Re-derived from the record's own fields on every access (never read from stored
        state), so a tampered stored id is ignored and ``from_dict(to_dict(r))``
        re-emits an identical id. Folds the engine version, the spec identity (extracted
        from the embedded request, including the declared ``cost_rate``), the source
        stability id + ``result_hash``, and the sealed ``result_hash`` over the answer.
        """
        spec = self.net_of_cost_spec
        return _netcost_id(
            net_of_cost_engine_version_id=self.net_of_cost_engine_version_id,
            name=_spec_str(spec, "name"),
            spec_version=_spec_str(spec, "spec_version"),
            source_stability_id=_spec_str(spec, "source_stability_id"),
            source_result_hash=self.source_ref[1],
            cost_rate=_spec_str(spec, "cost_rate"),
            result_hash=self.result_hash,
        )

    @property
    def research_result_id(self) -> str:
        """Alias of :attr:`net_of_cost_id` - the :class:`ResearchRecord` id."""
        return self.net_of_cost_id

    @property
    def source_stability_id(self) -> str:
        """The referenced source stability record's ``research_result_id``."""
        return self.source_ref[0]

    @property
    def source_result_hash(self) -> str:
        """The referenced source stability record's ``result_hash`` (the transitive
        pin)."""
        return self.source_ref[1]

    @property
    def net_status(self) -> NetCostStatus:
        """The roll-up net-of-cost status (a convenience alias of the summary's)."""
        return self.summary.net_status

    # -- sealing --------------------------------------------------------------

    @classmethod
    def seal(
        cls,
        *,
        net_of_cost_engine_version_id: str,
        net_of_cost_spec: dict[str, object],
        source_ref: tuple[str, str],
        boundary_kind: str,
        periods_per_year: str,
        risk_free_per_period: str,
        windows: tuple[WindowNetCostCell, ...],
        excluded: tuple[ExcludedWindow, ...],
        summary: NetOfCostSummary,
        coverage: NetOfCostCoverage,
        method_version: str = NETCOST_METHOD_VERSION,
    ) -> NetOfCostPerformance:
        """Seal computed blocks, folding the answer into ``result_hash`` (§10).

        The single constructor the engine uses: it folds the ordered computed-output
        cells (the coverage descriptor, the per-window net-cost cells, the excluded
        cells, then the aggregate summary) into ``result_hash`` via
        :func:`~quantforge.netcost.identity.net_of_cost_result_hash`, so identity is a
        pure function of the computed answer and never has to be supplied by the caller.
        The coverage block is a function of those cells and only its counts are folded,
        in the descriptor. The inherited ``periods_per_year`` / ``risk_free_per_period``
        conventions are carried metadata reflected through the net moments (which fold
        into ``result_hash``), not folded a second time - the walk-forward precedent.
        """
        rhash = _result_hash(
            _output_cells(
                windows=windows,
                excluded=excluded,
                summary=summary,
                coverage=coverage,
            )
        )
        return cls(
            net_of_cost_engine_version_id=net_of_cost_engine_version_id,
            net_of_cost_spec=dict(net_of_cost_spec),
            source_ref=source_ref,
            boundary_kind=boundary_kind,
            periods_per_year=periods_per_year,
            risk_free_per_period=risk_free_per_period,
            windows=windows,
            excluded=excluded,
            summary=summary,
            coverage=coverage,
            method_version=method_version,
            result_hash=rhash,
        )

    # -- serialization --------------------------------------------------------

    def to_dict(self) -> dict[str, object]:
        return {
            "net_of_cost_id": self.net_of_cost_id,
            # The ResearchRecord alias so the generic sidecar reader keys correctly.
            "research_result_id": self.research_result_id,
            "net_of_cost_engine_version_id": self.net_of_cost_engine_version_id,
            "net_of_cost_spec": dict(self.net_of_cost_spec),
            "source_ref": {
                "source_stability_id": self.source_ref[0],
                "source_result_hash": self.source_ref[1],
            },
            "boundary_kind": self.boundary_kind,
            "periods_per_year": self.periods_per_year,
            "risk_free_per_period": self.risk_free_per_period,
            "windows": [cell.to_dict() for cell in self.windows],
            "excluded": [cell.to_dict() for cell in self.excluded],
            "summary": self.summary.to_dict(),
            "coverage": self.coverage.to_dict(),
            "method_version": self.method_version,
            "result_hash": self.result_hash,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> NetOfCostPerformance:
        """Reconstruct a sealed net-of-cost record from its :meth:`to_dict` payload.

        The additive inverse of :meth:`to_dict`, so a record read back from the shared
        sidecar via ``store.read_as(id, NetOfCostPerformance.from_dict)`` is a
        first-class typed object. ``net_of_cost_id`` / ``research_result_id`` are
        derived aliases re-emitted by their properties (never read from state), every
        nested cell round-trips through its own fail-closed ``from_dict``, and the block
        order is
        preserved - so ``from_dict(to_dict(r))`` re-emits identical bytes and the same
        ``result_hash``, introducing no drift.
        """
        source = _req_dict(raw, "source_ref")
        return cls(
            net_of_cost_engine_version_id=_req_str(
                raw, "net_of_cost_engine_version_id"
            ),
            net_of_cost_spec=dict(_req_dict(raw, "net_of_cost_spec")),
            source_ref=(
                _req_str(source, "source_stability_id"),
                _req_str(source, "source_result_hash"),
            ),
            boundary_kind=_req_str(raw, "boundary_kind"),
            periods_per_year=_req_str(raw, "periods_per_year"),
            risk_free_per_period=_req_str(raw, "risk_free_per_period"),
            windows=tuple(
                WindowNetCostCell.from_dict(_as_dict(item, "windows"))
                for item in _req_list(raw, "windows")
            ),
            excluded=tuple(
                ExcludedWindow.from_dict(_as_dict(item, "excluded"))
                for item in _req_list(raw, "excluded")
            ),
            summary=NetOfCostSummary.from_dict(_req_dict(raw, "summary")),
            coverage=NetOfCostCoverage.from_dict(_req_dict(raw, "coverage")),
            method_version=_req_str(raw, "method_version"),
            result_hash=_req_str(raw, "result_hash"),
        )


def _output_cells(
    *,
    windows: tuple[WindowNetCostCell, ...],
    excluded: tuple[ExcludedWindow, ...],
    summary: NetOfCostSummary,
    coverage: NetOfCostCoverage,
) -> list[dict[str, object]]:
    """The ordered computed-output cells sealed into ``result_hash`` (§10).

    A single deterministic list - the coverage descriptor (window / realized / excluded
    / charged / period counts), then the per-window net-cost cells (``index`` +
    n_periods + gross + turnover + cost + net) in source window order, then the excluded
    cells (``index`` + reason), then the aggregate summary block - each tagged by its
    block so two structurally different records can never collide. The ids, request,
    and declared cost rate are folded into ``net_of_cost_id`` through the request +
    reference instead. Sensitive to every computed value.
    """
    cells: list[dict[str, object]] = [
        {
            "block": "coverage_descriptor",
            "n_windows": coverage.n_windows,
            "n_realized": coverage.n_realized,
            "n_excluded": coverage.n_excluded,
            "n_charged": coverage.n_charged,
            "n_periods": coverage.n_periods,
        }
    ]
    for cell in windows:
        cells.append({"block": "window", **cell.to_dict()})
    for gap in excluded:
        cells.append(
            {"block": "excluded", "index": gap.index, "reason": gap.reason.value}
        )
    cells.append({"block": "summary", **summary.to_dict()})
    return cells


def _spec_str(spec: dict[str, object], key: str) -> str:
    """Read a required string field from the embedded request payload (fail closed)."""
    value = spec.get(key)
    if not isinstance(value, str):
        raise ValueError(f"net_of_cost_spec.{key} must be a string")
    return value
