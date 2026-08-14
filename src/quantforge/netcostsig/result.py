"""The sealed, content-addressed net-of-cost-significance record (§9, §10).

A completed test is a :class:`NetOfCostSignificance`: the engine version, the full
declarative request, the ``(source_net_of_cost_id, source_result_hash)`` reference to
the one sealed :class:`~quantforge.netcost.result.NetOfCostPerformance` it consumed, the
aggregate :class:`SignificanceSummary` (the net mean carried verbatim, the null mean
tested, the period count, the standard error, the ``t`` statistic, the one-sided ``p``
value, the descriptive edge direction, and the roll-up status), and the sealed
``result_hash`` over the computed answer.

Like every research record in this project it satisfies the
:class:`~quantforge.factors.store.ResearchRecord` Protocol - ``research_result_id``
aliases ``net_of_cost_significance_id`` (a single id, mirroring
``calibration_significance_id``) and ``to_dict`` is deterministic - so it persists
write-once to the shared Phase 8 sidecar with **no new store** (§13). It stores only a
*pointer* to the source net-of-cost record, never a copy of its windows (the
pointer-only discipline of :class:`~quantforge.calsig.result.CalibrationSignificance`):
the source already lives in the same sidecar, so this record stays a thin, reproducible
view over it.

**Ex-post, not PIT (NS-6).** A significance test over an already-ex-post (and
counterfactual) net-of-cost analysis is itself an ex-post research statistic, not a
forward-usable PIT value. :class:`NetOfCostSignificance` is deliberately **not** a
``Pit*`` type and exposes **no** as-of accessor. ``boundary_kind = "pit"`` documents
only that the *underlying factor portfolios* were PIT walks - the convention where the
label describes the input side, not the ex-post output. It is not a ``BacktestResult``
and performs no execution.

Every value is deterministically serializable and round-trips byte-identically through
:meth:`~NetOfCostSignificance.from_dict`; the derived ids are re-emitted by their
properties, never read from stored state. No wall-clock, RNG, or iteration-order
dependence enters any value or id.
"""

from __future__ import annotations

from dataclasses import dataclass

from quantforge.netcostsig.identity import (
    net_of_cost_significance_id as _netcostsig_id,
)
from quantforge.netcostsig.identity import (
    net_of_cost_significance_result_hash as _result_hash,
)
from quantforge.netcostsig.model import (
    EdgeDirection,
    NetCostSigUndefinedReason,
    SignificanceStat,
    SignificanceStatus,
)
from quantforge.netcostsig.version import NETCOSTSIG_METHOD_VERSION

__all__ = [
    "BOUNDARY_PIT",
    "NETCOSTSIG_RESULT_FORMAT_VERSION",
    "NULL_MEAN_RETURN",
    "NetOfCostSignificance",
    "SignificanceSummary",
]

#: The §9 record-schema version for the significance record - distinct from the
#: engine-logic version, the method version, the normal-primitive version, and the
#: sidecar's container format version. Bump it when the serialized meaning of a
#: significance record changes (a container concern; it is **not** folded into
#: ``net_of_cost_significance_id`` - §10, prior-phase discipline).
NETCOSTSIG_RESULT_FORMAT_VERSION = "netcostsig-result/1"

#: The only boundary a v1 significance record accepts. It documents that the *underlying
#: factor portfolios* (beneath the source net-of-cost record's walk-forward) were PIT
#: walks; the significance *output* is ex-post and is not a PIT value (NS-6). The engine
#: carries the source net-of-cost record's ``boundary_kind`` through unchanged.
BOUNDARY_PIT = "pit"

#: The null mean tested: no after-cost edge is a mean return of ``0`` (a strategy that
#: earns nothing after paying to trade). A fixed platform constant (the single approved
#: methodology has no per-request numerical parameter), folded into
#: ``net_of_cost_significance_id`` (§10) - as Phase 29 folds ``NULL_MEAN_RATIO`` - so a
#: change to it is a distinguishable record.
NULL_MEAN_RETURN = "0"


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


@dataclass(frozen=True, slots=True)
class SignificanceSummary:
    """The aggregate one-sample significance statistics + the roll-up status (§9).

    ``net_mean`` is the source's KNOWN after-cost mean carried verbatim (NS-4);
    ``null_mean_return`` the hypothesized mean tested (``0``); ``n_periods`` the
    source's net-series period count ``n``. ``standard_error`` / ``t_statistic`` /
    ``p_value`` are UNDEFINED-preserving
    :class:`~quantforge.netcostsig.model.SignificanceStat` cells; ``edge_direction`` the
    descriptive sign of the after-cost edge (``None`` when the source is not MEASURED);
    and ``significance_status`` (``TESTED`` when ``t`` / ``p`` are KNOWN, else
    ``UNDEFINED`` with ``status_reason``). With a non-MEASURED source every statistic is
    UNDEFINED (``SOURCE_NOT_MEASURED``); the record still seals (NS-2).
    """

    net_mean: SignificanceStat
    null_mean_return: str
    n_periods: int
    standard_error: SignificanceStat
    t_statistic: SignificanceStat
    p_value: SignificanceStat
    significance_status: SignificanceStatus
    edge_direction: EdgeDirection | None = None
    status_reason: NetCostSigUndefinedReason | None = None

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "net_mean": self.net_mean.to_dict(),
            "null_mean_return": self.null_mean_return,
            "n_periods": self.n_periods,
            "standard_error": self.standard_error.to_dict(),
            "t_statistic": self.t_statistic.to_dict(),
            "p_value": self.p_value.to_dict(),
            "significance_status": self.significance_status.value,
        }
        if self.edge_direction is not None:
            payload["edge_direction"] = self.edge_direction.value
        if self.status_reason is not None:
            payload["status_reason"] = self.status_reason.value
        return payload

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> SignificanceSummary:
        def _cell(key: str) -> SignificanceStat:
            value = raw.get(key)
            if not isinstance(value, dict):
                raise ValueError(f"SignificanceSummary.{key} must be an object")
            return SignificanceStat.from_dict(value)

        status_raw = _req_str(raw, "significance_status")
        try:
            status = SignificanceStatus(status_raw)
        except ValueError as exc:
            raise ValueError(f"unknown significance_status {status_raw!r}") from exc

        direction_raw = raw.get("edge_direction")
        direction: EdgeDirection | None
        if direction_raw is None:
            direction = None
        elif isinstance(direction_raw, str):
            try:
                direction = EdgeDirection(direction_raw)
            except ValueError as exc:
                raise ValueError(f"unknown edge_direction {direction_raw!r}") from exc
        else:
            raise ValueError(
                "SignificanceSummary.edge_direction must be a string or absent"
            )

        reason_raw = raw.get("status_reason")
        reason: NetCostSigUndefinedReason | None
        if reason_raw is None:
            reason = None
        elif isinstance(reason_raw, str):
            try:
                reason = NetCostSigUndefinedReason(reason_raw)
            except ValueError as exc:
                raise ValueError(
                    f"unknown NetCostSigUndefinedReason {reason_raw!r}"
                ) from exc
        else:
            raise ValueError(
                "SignificanceSummary.status_reason must be a string or absent"
            )

        return cls(
            net_mean=_cell("net_mean"),
            null_mean_return=_req_str(raw, "null_mean_return"),
            n_periods=_req_int(raw, "n_periods"),
            standard_error=_cell("standard_error"),
            t_statistic=_cell("t_statistic"),
            p_value=_cell("p_value"),
            significance_status=status,
            edge_direction=direction,
            status_reason=reason,
        )


@dataclass(frozen=True, slots=True)
class NetOfCostSignificance:
    """A sealed, content-addressed net-of-cost-significance record (§9).

    Implements the :class:`~quantforge.factors.store.ResearchRecord` Protocol
    (:attr:`research_result_id` aliases :attr:`net_of_cost_significance_id`;
    deterministic :meth:`to_dict`), so it persists write-once to the shared research
    sidecar with no new store. It pins the source net-of-cost record by
    ``(id, result_hash)``, holds the aggregate significance summary, and seals the
    computed answer into ``result_hash``. It is **not** a ``Pit*`` type and exposes no
    as-of accessor (NS-6).
    """

    net_of_cost_significance_engine_version_id: str
    net_of_cost_significance_spec: dict[str, object]
    source_ref: tuple[str, str]
    boundary_kind: str
    summary: SignificanceSummary
    method_version: str
    result_hash: str

    # -- derived ids (never stored as state) ---------------------------------

    @property
    def net_of_cost_significance_id(self) -> str:
        """The content-addressed id - request, referenced content, **and** answer (§10).

        Re-derived from the record's own fields on every access (never read from stored
        state), so a tampered stored id is ignored and ``from_dict(to_dict(r))``
        re-emits an identical id. Folds the engine version, the spec identity (extracted
        from the embedded request), the source net-of-cost id + ``result_hash``, the
        :data:`NULL_MEAN_RETURN` tested, and the sealed ``result_hash`` over the answer.
        """
        spec = self.net_of_cost_significance_spec
        return _netcostsig_id(
            net_of_cost_significance_engine_version_id=(
                self.net_of_cost_significance_engine_version_id
            ),
            name=_spec_str(spec, "name"),
            spec_version=_spec_str(spec, "spec_version"),
            source_net_of_cost_id=_spec_str(spec, "source_net_of_cost_id"),
            source_result_hash=self.source_ref[1],
            null_mean_return=self.summary.null_mean_return,
            result_hash=self.result_hash,
        )

    @property
    def research_result_id(self) -> str:
        """Alias of :attr:`net_of_cost_significance_id` - the :class:`ResearchRecord`
        id."""
        return self.net_of_cost_significance_id

    @property
    def source_net_of_cost_id(self) -> str:
        """The referenced source net-of-cost record's ``research_result_id``."""
        return self.source_ref[0]

    @property
    def source_result_hash(self) -> str:
        """The referenced source net-of-cost record's ``result_hash`` (the transitive
        pin)."""
        return self.source_ref[1]

    @property
    def significance_status(self) -> SignificanceStatus:
        """The roll-up significance status (a convenience alias of the summary's)."""
        return self.summary.significance_status

    # -- sealing --------------------------------------------------------------

    @classmethod
    def seal(
        cls,
        *,
        net_of_cost_significance_engine_version_id: str,
        net_of_cost_significance_spec: dict[str, object],
        source_ref: tuple[str, str],
        boundary_kind: str,
        summary: SignificanceSummary,
        method_version: str = NETCOSTSIG_METHOD_VERSION,
    ) -> NetOfCostSignificance:
        """Seal the computed summary, folding the answer into ``result_hash`` (§10).

        The single constructor the engine uses: it folds the ordered computed-output
        cells (the single aggregate summary block) into ``result_hash`` via
        :func:`~quantforge.netcostsig.identity.net_of_cost_significance_result_hash`, so
        identity is a pure function of the computed answer and never has to be supplied
        by the caller.
        """
        rhash = _result_hash(_output_cells(summary=summary))
        return cls(
            net_of_cost_significance_engine_version_id=(
                net_of_cost_significance_engine_version_id
            ),
            net_of_cost_significance_spec=dict(net_of_cost_significance_spec),
            source_ref=source_ref,
            boundary_kind=boundary_kind,
            summary=summary,
            method_version=method_version,
            result_hash=rhash,
        )

    # -- serialization --------------------------------------------------------

    def to_dict(self) -> dict[str, object]:
        return {
            "net_of_cost_significance_id": self.net_of_cost_significance_id,
            # The ResearchRecord alias so the generic sidecar reader keys correctly.
            "research_result_id": self.research_result_id,
            "net_of_cost_significance_engine_version_id": (
                self.net_of_cost_significance_engine_version_id
            ),
            "net_of_cost_significance_spec": dict(self.net_of_cost_significance_spec),
            "source_ref": {
                "source_net_of_cost_id": self.source_ref[0],
                "source_result_hash": self.source_ref[1],
            },
            "boundary_kind": self.boundary_kind,
            "summary": self.summary.to_dict(),
            "method_version": self.method_version,
            "result_hash": self.result_hash,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> NetOfCostSignificance:
        """Reconstruct a sealed significance record from its :meth:`to_dict` payload.

        The additive inverse of :meth:`to_dict`, so a record read back from the shared
        sidecar via ``store.read_as(id, NetOfCostSignificance.from_dict)`` is a
        first-class typed object. ``net_of_cost_significance_id`` /
        ``research_result_id`` are derived aliases re-emitted by their properties (never
        read from state), the nested summary round-trips through its own fail-closed
        ``from_dict`` - so ``from_dict(to_dict(r))`` re-emits identical bytes and the
        same ``result_hash``, introducing no drift.
        """
        source = _req_dict(raw, "source_ref")
        return cls(
            net_of_cost_significance_engine_version_id=_req_str(
                raw, "net_of_cost_significance_engine_version_id"
            ),
            net_of_cost_significance_spec=dict(
                _req_dict(raw, "net_of_cost_significance_spec")
            ),
            source_ref=(
                _req_str(source, "source_net_of_cost_id"),
                _req_str(source, "source_result_hash"),
            ),
            boundary_kind=_req_str(raw, "boundary_kind"),
            summary=SignificanceSummary.from_dict(_req_dict(raw, "summary")),
            method_version=_req_str(raw, "method_version"),
            result_hash=_req_str(raw, "result_hash"),
        )


def _output_cells(*, summary: SignificanceSummary) -> list[dict[str, object]]:
    """The ordered computed-output cells sealed into ``result_hash`` (§10).

    A single deterministic list - the aggregate significance summary block, tagged by
    its block so two structurally different records can never collide. The ids, request,
    and null mean are folded into ``net_of_cost_significance_id`` through the request +
    reference instead. Sensitive to every computed statistic.
    """
    return [{"block": "summary", **summary.to_dict()}]


def _spec_str(spec: dict[str, object], key: str) -> str:
    """Read a required string field from the embedded request payload (fail closed)."""
    value = spec.get(key)
    if not isinstance(value, str):
        raise ValueError(f"net_of_cost_significance_spec.{key} must be a string")
    return value
