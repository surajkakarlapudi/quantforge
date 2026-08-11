"""The sealed, content-addressed factor-risk record (§9, §10).

A completed factor-risk estimation is a :class:`FactorRiskModel`: the engine version,
the full declarative request, the ordered ``(label, factor_portfolio_id, result_hash)``
reference to each factor (in request order), the shared ``schedule_id`` and producing
``factor_portfolio_engine_version_id``, the analysed common-window period count, the
per-factor moment records, the upper-triangle covariance and correlation matrices (each
an ordered tuple of UNDEFINED-preserving
:class:`~quantforge.factorrisk.model.StatValue` cells), the coverage summary (audit
only), the recorded annualization convention, the carried-through corpus pins, and the
sealed ``result_hash`` over the computed answer.

Like every research record in this project it satisfies the
:class:`~quantforge.factors.store.ResearchRecord` Protocol - ``research_result_id``
aliases ``factor_risk_id`` (a single id, mirroring ``attribution_id`` /
``factor_portfolio_id``) and ``to_dict`` is deterministic - so it persists write-once to
the shared Phase 8 sidecar with **no new store** (§13). It stores only *pointers* to the
referenced factor portfolios, never a copy of their return series (the pointer-only
discipline of :class:`~quantforge.attribution.result.FactorAttribution`): the referenced
records already live in the same sidecar, so this record stays a thin, reproducible
index over them.

**Ex-post, not PIT (FR-2).** A covariance/correlation matrix of realized factor returns
is an ex-post research statistic, not a forward-usable PIT value.
:class:`FactorRiskModel` is deliberately **not** a ``Pit*`` type and exposes **no**
as-of accessor: it can never be handed to a layer that requires a PIT signal.
``boundary_kind = "pit"`` documents only that the *underlying factor portfolios were PIT
walks* - the Phase 16 SD-2 convention where the label describes the input side, not the
ex-post output.

Every value is deterministically serializable and round-trips byte-identically through
:meth:`~FactorRiskModel.from_dict`; the derived ids are re-emitted by their properties,
never read from stored state, so a tampered stored id is ignored and
``from_dict(to_dict(r))`` re-emits identical bytes. No wall-clock, RNG, or
iteration-order dependence enters any value or id.
"""

from __future__ import annotations

from dataclasses import dataclass

from quantforge.factorrisk.identity import factor_risk_id as _factor_risk_id
from quantforge.factorrisk.identity import factor_risk_result_hash as _result_hash
from quantforge.factorrisk.model import (
    CorrelationCell,
    CovarianceCell,
    CoverageSummary,
    FactorMoment,
)
from quantforge.factorrisk.version import FACTORRISK_FORMULA_VERSION

__all__ = [
    "BOUNDARY_PIT",
    "FACTORRISK_RESULT_FORMAT_VERSION",
    "FactorRiskModel",
]

#: The §9 record-schema version for the factor-risk record - distinct from the
#: engine-logic version, the formula version, and the sidecar's container format
#: version.
#: Bump it when the serialized meaning of a factor-risk record changes (a container
#: concern; it is **not** folded into ``factor_risk_id`` - §10, Phase 17/19 discipline).
FACTORRISK_RESULT_FORMAT_VERSION = "factorrisk-result/1"

#: The only boundary a v1 factor-risk record accepts (§7, inv. 27/28). Factor portfolios
#: are PIT-only by construction, so their return series are PIT-only; the record carries
#: this explicit, un-defaulted value and the engine sets it unconditionally. It
#: documents the *input* side (the underlying factor portfolios were PIT walks); the
#: factor-risk
#: *output* is ex-post and is not a PIT value (FR-2). A REVISED risk scope is reserved
#: for
#: a future explicitly-labelled phase.
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


def _as_str(value: object, key: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"each {key} entry must be a string")
    return value


def _factor_refs(items: list[object]) -> tuple[tuple[str, str, str], ...]:
    """Decode the ordered factor references into ``(label, id, result_hash)``
    triples."""
    out: list[tuple[str, str, str]] = []
    for item in items:
        raw = _as_dict(item, "factor_refs")
        label = raw.get("label")
        if not isinstance(label, str):
            raise ValueError("each factor_refs entry must carry a string label")
        ref = raw.get("ref")
        if (
            not isinstance(ref, list)
            or len(ref) != 2
            or not all(isinstance(item, str) for item in ref)
        ):
            raise ValueError(
                "each factor_refs.ref must be an [id, result_hash] string pair"
            )
        out.append((label, ref[0], ref[1]))
    return tuple(out)


@dataclass(frozen=True, slots=True)
class FactorRiskModel:
    """A sealed, content-addressed factor covariance/correlation record (§9).

    Implements the :class:`~quantforge.factors.store.ResearchRecord` Protocol
    (:attr:`research_result_id` aliases :attr:`factor_risk_id`; deterministic
    :meth:`to_dict`), so it persists write-once to the shared research sidecar with no
    new store. It pins each factor by ``(label, factor_portfolio_id, result_hash)`` in
    request order, records the shared schedule and producing engine version and the
    analysed
    common-window period count, holds the per-factor moments and the upper-triangle
    covariance / correlation matrices, keeps the coverage summary for audit, carries the
    referenced corpus pins, and seals the computed answer into ``result_hash`` - so its
    identity is a pure function of the request, the referenced content, and the computed
    statistics. It is **not** a ``Pit*`` type and exposes no as-of accessor (FR-2).
    """

    factor_risk_engine_version_id: str
    factor_risk_spec: dict[str, object]
    factor_refs: tuple[tuple[str, str, str], ...]
    boundary_kind: str
    schedule_id: str
    factor_portfolio_engine_version_id: str
    periods: int
    periods_per_year: str
    factors: tuple[FactorMoment, ...]
    covariance: tuple[CovarianceCell, ...]
    correlation: tuple[CorrelationCell, ...]
    coverage: CoverageSummary
    dataset_version_ids: tuple[str, ...]
    market_dataset_version_ids: tuple[str, ...]
    formula_version: str
    result_hash: str

    # -- derived ids (never stored as state) ---------------------------------

    @property
    def factor_risk_id(self) -> str:
        """The content-addressed id - request, referenced content, **and** answer (§10).

        Re-derived from the record's own fields on every access (never read from stored
        state), so a tampered stored id is ignored and ``from_dict(to_dict(r))``
        re-emits an identical id. Folds the engine version, the spec identity (extracted
        from the embedded request), the ordered factor ``result_hash``es, and the sealed
        ``result_hash`` over the computed answer.
        """
        spec = self.factor_risk_spec
        return _factor_risk_id(
            factor_risk_engine_version_id=self.factor_risk_engine_version_id,
            name=_spec_str(spec, "name"),
            spec_version=_spec_str(spec, "spec_version"),
            factor_portfolio_ids=[ref[1] for ref in self.factor_refs],
            periods_per_year=self.periods_per_year,
            factor_result_hashes=[ref[2] for ref in self.factor_refs],
            result_hash=self.result_hash,
        )

    @property
    def research_result_id(self) -> str:
        """Alias of :attr:`factor_risk_id` - the :class:`ResearchRecord` identity."""
        return self.factor_risk_id

    @property
    def factor_portfolio_ids(self) -> tuple[str, ...]:
        """The referenced factor ids, in request order (the matrix row/column order)."""
        return tuple(ref[1] for ref in self.factor_refs)

    @property
    def pin_mismatch(self) -> bool:
        """True iff the factors differ on any carried corpus pin (§9, FR-3).

        Surfaced, never raised (mirrors ``FactorAttribution.pin_mismatch``): a model may
        legitimately estimate the risk of factors run over a different corpus snapshot,
        but a reader must be able to see that the references were not pinned
        identically.
        Flagged when more than one distinct pin appears in either the fundamentals or
        the market dimension. (Commensurability - one ``schedule_id`` and one producing
        engine
        version - is a separate, *raised* contract, FR-3.)
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
        factor_risk_engine_version_id: str,
        factor_risk_spec: dict[str, object],
        factor_refs: tuple[tuple[str, str, str], ...],
        boundary_kind: str,
        schedule_id: str,
        factor_portfolio_engine_version_id: str,
        periods: int,
        periods_per_year: str,
        factors: tuple[FactorMoment, ...],
        covariance: tuple[CovarianceCell, ...],
        correlation: tuple[CorrelationCell, ...],
        coverage: CoverageSummary,
        dataset_version_ids: tuple[str, ...],
        market_dataset_version_ids: tuple[str, ...],
        formula_version: str = FACTORRISK_FORMULA_VERSION,
    ) -> FactorRiskModel:
        """Seal computed blocks, folding the answer into ``result_hash`` (§10).

        The single constructor the engine uses: it folds the ordered computed-output
        cells (the per-factor moments, then the upper-triangle covariance cells, then
        the upper-triangle correlation cells) into ``result_hash`` via
        :func:`~quantforge.factorrisk.identity.factor_risk_result_hash`, so identity is
        a pure function of the computed answer and never has to be supplied by the
        caller.
        The coverage summary is **not** folded (audit metadata fully determined by the
        inputs).
        """
        rhash = _result_hash(
            _output_cells(
                factors=factors,
                covariance=covariance,
                correlation=correlation,
            )
        )
        return cls(
            factor_risk_engine_version_id=factor_risk_engine_version_id,
            factor_risk_spec=dict(factor_risk_spec),
            factor_refs=factor_refs,
            boundary_kind=boundary_kind,
            schedule_id=schedule_id,
            factor_portfolio_engine_version_id=factor_portfolio_engine_version_id,
            periods=periods,
            periods_per_year=periods_per_year,
            factors=factors,
            covariance=covariance,
            correlation=correlation,
            coverage=coverage,
            dataset_version_ids=dataset_version_ids,
            market_dataset_version_ids=market_dataset_version_ids,
            formula_version=formula_version,
            result_hash=rhash,
        )

    # -- serialization --------------------------------------------------------

    def to_dict(self) -> dict[str, object]:
        return {
            "factor_risk_id": self.factor_risk_id,
            # The ResearchRecord alias so the generic sidecar reader keys correctly.
            "research_result_id": self.research_result_id,
            "factor_risk_engine_version_id": self.factor_risk_engine_version_id,
            "factor_risk_spec": dict(self.factor_risk_spec),
            "factor_refs": [
                {"label": label, "ref": [factor_portfolio_id, result_hash]}
                for label, factor_portfolio_id, result_hash in self.factor_refs
            ],
            "boundary_kind": self.boundary_kind,
            "schedule_id": self.schedule_id,
            "factor_portfolio_engine_version_id": (
                self.factor_portfolio_engine_version_id
            ),
            "periods": self.periods,
            "periods_per_year": self.periods_per_year,
            "factors": [moment.to_dict() for moment in self.factors],
            "covariance": [cell.to_dict() for cell in self.covariance],
            "correlation": [cell.to_dict() for cell in self.correlation],
            "coverage": self.coverage.to_dict(),
            "dataset_version_ids": list(self.dataset_version_ids),
            "market_dataset_version_ids": list(self.market_dataset_version_ids),
            "formula_version": self.formula_version,
            "result_hash": self.result_hash,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> FactorRiskModel:
        """Reconstruct a sealed factor-risk record from its :meth:`to_dict` payload.

        The additive inverse of :meth:`to_dict`, so a record read back from the shared
        sidecar via ``store.read_as(id, FactorRiskModel.from_dict)`` is a first-class
        typed object. ``factor_risk_id`` / ``research_result_id`` are derived aliases
        re-emitted by their properties (never read from state), every nested cell
        round-trips through its own fail-closed ``from_dict``, and the block order is
        preserved - so ``from_dict(to_dict(r))`` re-emits identical bytes and the same
        ``result_hash``, introducing no drift.
        """
        return cls(
            factor_risk_engine_version_id=_req_str(
                raw, "factor_risk_engine_version_id"
            ),
            factor_risk_spec=dict(_req_dict(raw, "factor_risk_spec")),
            factor_refs=_factor_refs(_req_list(raw, "factor_refs")),
            boundary_kind=_req_str(raw, "boundary_kind"),
            schedule_id=_req_str(raw, "schedule_id"),
            factor_portfolio_engine_version_id=_req_str(
                raw, "factor_portfolio_engine_version_id"
            ),
            periods=_req_int(raw, "periods"),
            periods_per_year=_req_str(raw, "periods_per_year"),
            factors=tuple(
                FactorMoment.from_dict(_as_dict(item, "factors"))
                for item in _req_list(raw, "factors")
            ),
            covariance=tuple(
                CovarianceCell.from_dict(_as_dict(item, "covariance"))
                for item in _req_list(raw, "covariance")
            ),
            correlation=tuple(
                CorrelationCell.from_dict(_as_dict(item, "correlation"))
                for item in _req_list(raw, "correlation")
            ),
            coverage=CoverageSummary.from_dict(_req_dict(raw, "coverage")),
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
    factors: tuple[FactorMoment, ...],
    covariance: tuple[CovarianceCell, ...],
    correlation: tuple[CorrelationCell, ...],
) -> list[dict[str, object]]:
    """The ordered computed-output cells sealed into ``result_hash`` (§10).

    A single deterministic list - the per-factor moment cells in factor order, then the
    upper-triangle covariance cells, then the upper-triangle correlation cells - each
    cell tagged by its block so two structurally different records can never collide,
    and each
    reduced to its canonical form. Sensitive to every computed statistic: one differing
    cell changes ``result_hash`` and therefore ``factor_risk_id``. The coverage summary
    is deliberately excluded (audit metadata fully determined by the inputs).
    """
    cells: list[dict[str, object]] = []
    for moment in factors:
        cells.append(
            {
                "block": "factor",
                "label": moment.label,
                "mean": moment.mean.to_dict(),
                "volatility": moment.volatility.to_dict(),
                "annualized_volatility": moment.annualized_volatility.to_dict(),
            }
        )
    for cell in covariance:
        cells.append(
            {
                "block": "cov",
                "i": cell.i,
                "j": cell.j,
                "value": cell.value.to_dict(),
                "annualized": cell.annualized.to_dict(),
            }
        )
    for corr_cell in correlation:
        cells.append(
            {
                "block": "corr",
                "i": corr_cell.i,
                "j": corr_cell.j,
                "value": corr_cell.value.to_dict(),
            }
        )
    return cells


def _spec_str(spec: dict[str, object], key: str) -> str:
    """Read a required string field from the embedded request payload (fail closed)."""
    value = spec.get(key)
    if not isinstance(value, str):
        raise ValueError(f"factor_risk_spec.{key} must be a string")
    return value
