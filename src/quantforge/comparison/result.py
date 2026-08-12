"""The sealed, content-addressed strategy-comparison record (§9, §10).

A completed comparison is a :class:`StrategyComparison`: the engine version, the full
declarative request, the ordered ``(label, walk_forward_id, result_hash)`` reference to
each strategy (in request order), the shared ``schedule_id`` / producing
``factor_portfolio_engine_version_id`` / ``periods_per_year`` /
``risk_free_per_period``, the per-strategy summary block (the sealed annualized OOS
Sharpe, the valid-period count, the reconstructed axis length), the upper-triangle
matrix of pairwise paired-difference cells, a non-hashed coverage block, the
carried-through corpus pins, and the sealed ``result_hash`` over the computed answer.

Like every research record in this project it satisfies the
:class:`~quantforge.factors.store.ResearchRecord` Protocol - ``research_result_id``
aliases ``strategy_comparison_id`` (a single id, mirroring ``campaign_id``) and
``to_dict`` is deterministic - so it persists write-once to the shared Phase 8 sidecar
with **no new store**. It stores only *pointers* to the referenced strategies, never a
copy of their return series (the pointer-only discipline of
:class:`~quantforge.campaign.result.ResearchCampaignEvaluation`): the referenced
records already live in the same sidecar, so this record stays a thin, reproducible
index over them.

**Ex-post, not PIT (SC-6).** A pairwise out-of-sample comparison is an ex-post research
statistic, not a forward-usable PIT value. :class:`StrategyComparison` is deliberately
**not** a ``Pit*`` type and exposes **no** as-of accessor. ``boundary_kind = "pit"``
documents only that the *underlying strategies were PIT walks* - the convention where
the label describes the input side, not the ex-post output.

**Antisymmetry (SC-8).** Only the ``i < j`` upper triangle is sealed;
:meth:`~StrategyComparison.cell` reads either orientation, sign-flipping ``mean_diff`` /
``t_stat`` / ``sharpe_diff`` for ``(j, i)`` while preserving ``p_value`` /
``overlap_periods``.

Every value is deterministically serializable and round-trips byte-identically through
:meth:`~StrategyComparison.from_dict`; the derived ids are re-emitted by their
properties, never read from stored state. No wall-clock, RNG, or iteration-order
dependence enters any value or id.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from quantforge.comparison.identity import (
    strategy_comparison_id as _strategy_comparison_id,
)
from quantforge.comparison.identity import (
    strategy_comparison_result_hash as _result_hash,
)
from quantforge.comparison.model import (
    ComparisonStatus,
    ComparisonUndefinedReason,
    StatStatus,
    StatValue,
)
from quantforge.comparison.version import COMPARISON_METHOD_VERSION

__all__ = [
    "BOUNDARY_PIT",
    "COMPARISON_RESULT_FORMAT_VERSION",
    "ComparisonCell",
    "Coverage",
    "StrategyComparison",
    "TrialSummary",
]

#: The §9 record-schema version for the comparison record - distinct from the
#: engine-logic version, the method version, the normal-primitive version, and the
#: sidecar's container format version. Bump it when the serialized meaning of a
#: comparison record changes (a container concern; it is **not** folded into
#: ``strategy_comparison_id`` - §10, prior-phase discipline).
COMPARISON_RESULT_FORMAT_VERSION = "comparison-result/1"

#: The only boundary a v1 comparison record accepts. Walk-forward strategies are
#: PIT-only by construction, so their OOS return series are PIT-only; the record carries
#: this explicit, un-defaulted value and the engine sets it unconditionally. It
#: documents the *input* side; the comparison *output* is ex-post and is not a PIT value
#: (SC-6).
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


def _opt_reason(raw: dict[str, object]) -> ComparisonUndefinedReason | None:
    """Decode an optional pair-level ``reason`` string (fail closed)."""
    reason_raw = raw.get("reason")
    if reason_raw is None:
        return None
    if not isinstance(reason_raw, str):
        raise ValueError("ComparisonCell.reason must be a string or absent")
    try:
        return ComparisonUndefinedReason(reason_raw)
    except ValueError as exc:
        raise ValueError(f"unknown ComparisonUndefinedReason {reason_raw!r}") from exc


def _strategy_refs(items: list[object]) -> tuple[tuple[str, str, str], ...]:
    """Decode the ordered strategy references into ``(label, id, result_hash)``."""
    out: list[tuple[str, str, str]] = []
    for item in items:
        raw = _as_dict(item, "strategy_refs")
        label = raw.get("label")
        if not isinstance(label, str):
            raise ValueError("each strategy_refs entry must carry a string label")
        ref = raw.get("ref")
        if (
            not isinstance(ref, list)
            or len(ref) != 2
            or not all(isinstance(part, str) for part in ref)
        ):
            raise ValueError(
                "each strategy_refs.ref must be an [id, result_hash] string pair"
            )
        out.append((label, ref[0], ref[1]))
    return tuple(out)


@dataclass(frozen=True, slots=True)
class TrialSummary:
    """One strategy's sealed summary block (§9).

    ``label`` is ``strategy_1..strategy_N`` in request order; ``sharpe`` is the
    strategy's sealed annualized OOS Sharpe as an UNDEFINED-preserving cell (KNOWN for a
    defined Sharpe, UNDEFINED ``UNDEFINED_STRATEGY_SHARPE`` when the walk's own Sharpe
    was undefined); ``n_valid_periods`` is the sealed count of valid OOS periods;
    ``axis_periods`` is the reconstructed complete-case axis length (the strategy's
    ``common_periods``). The referenced id lives in the record's ``strategy_refs``.
    """

    label: str
    sharpe: StatValue
    n_valid_periods: int
    axis_periods: int

    def to_dict(self) -> dict[str, object]:
        return {
            "label": self.label,
            "sharpe": self.sharpe.to_dict(),
            "n_valid_periods": self.n_valid_periods,
            "axis_periods": self.axis_periods,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> TrialSummary:
        return cls(
            label=_req_str(raw, "label"),
            sharpe=StatValue.from_dict(_req_dict(raw, "sharpe")),
            n_valid_periods=_req_int(raw, "n_valid_periods"),
            axis_periods=_req_int(raw, "axis_periods"),
        )


@dataclass(frozen=True, slots=True)
class ComparisonCell:
    """One sealed upper-triangle ``(i < j)`` paired-difference cell (§9, SC-4/SC-8).

    ``status`` is ``KNOWN`` when the pair overlaps in at least
    :data:`~quantforge.comparison.compute.MIN_OVERLAP_PERIODS` dates and ``UNDEFINED``
    (with ``reason = INSUFFICIENT_OVERLAP``) otherwise. ``mean_diff`` /
    ``stderr_diff`` / ``t_stat`` / ``p_value`` / ``sharpe_diff`` are
    UNDEFINED-preserving cells; a KNOWN pair may still carry an UNDEFINED ``t_stat`` /
    ``p_value`` (zero difference variance) or ``sharpe_diff`` (an undefined leg
    Sharpe). ``overlap_periods`` is the shared-date
    count. ``label_i`` / ``label_j`` are the ``strategy_k`` labels (derivable from
    ``i`` / ``j``; carried for readability, excluded from the hash).
    """

    i: int
    j: int
    label_i: str
    label_j: str
    status: ComparisonStatus
    overlap_periods: int
    mean_diff: StatValue
    stderr_diff: StatValue
    t_stat: StatValue
    p_value: StatValue
    sharpe_diff: StatValue
    reason: ComparisonUndefinedReason | None = None

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "i": self.i,
            "j": self.j,
            "label_i": self.label_i,
            "label_j": self.label_j,
            "status": self.status.value,
            "overlap_periods": self.overlap_periods,
            "mean_diff": self.mean_diff.to_dict(),
            "stderr_diff": self.stderr_diff.to_dict(),
            "t_stat": self.t_stat.to_dict(),
            "p_value": self.p_value.to_dict(),
            "sharpe_diff": self.sharpe_diff.to_dict(),
        }
        if self.reason is not None:
            payload["reason"] = self.reason.value
        return payload

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> ComparisonCell:
        status_raw = _req_str(raw, "status")
        try:
            status = ComparisonStatus(status_raw)
        except ValueError as exc:
            raise ValueError(f"unknown comparison status {status_raw!r}") from exc
        return cls(
            i=_req_int(raw, "i"),
            j=_req_int(raw, "j"),
            label_i=_req_str(raw, "label_i"),
            label_j=_req_str(raw, "label_j"),
            status=status,
            overlap_periods=_req_int(raw, "overlap_periods"),
            mean_diff=StatValue.from_dict(_req_dict(raw, "mean_diff")),
            stderr_diff=StatValue.from_dict(_req_dict(raw, "stderr_diff")),
            t_stat=StatValue.from_dict(_req_dict(raw, "t_stat")),
            p_value=StatValue.from_dict(_req_dict(raw, "p_value")),
            sharpe_diff=StatValue.from_dict(_req_dict(raw, "sharpe_diff")),
            reason=_opt_reason(raw),
        )

    def transpose(self) -> ComparisonCell:
        """The ``(j, i)`` view of this ``(i, j)`` cell (SC-8, antisymmetry).

        Sign-flips the antisymmetric cells (``mean_diff`` / ``t_stat`` /
        ``sharpe_diff``) and swaps the labels, preserving the symmetric ``p_value`` /
        ``overlap_periods`` - the exact statistics a ``(j, i)`` computation would have
        produced. UNDEFINED cells are preserved unchanged (there is nothing to negate).
        """
        return ComparisonCell(
            i=self.j,
            j=self.i,
            label_i=self.label_j,
            label_j=self.label_i,
            status=self.status,
            overlap_periods=self.overlap_periods,
            mean_diff=_negate(self.mean_diff),
            stderr_diff=self.stderr_diff,
            t_stat=_negate(self.t_stat),
            p_value=self.p_value,
            sharpe_diff=_negate(self.sharpe_diff),
            reason=self.reason,
        )


@dataclass(frozen=True, slots=True)
class Coverage:
    """The audit coverage block - counts of strategies and pairs (§9).

    Excluded from ``result_hash`` (it is a pure function of the sealed cells - a
    reader's convenience, not an independent input): ``n_strategies`` strategies form
    ``n_pairs = n·(n-1)/2`` upper-triangle pairs, of which ``n_defined_pairs`` are KNOWN
    and ``n_undefined_pairs`` are UNDEFINED (too little overlap).
    """

    n_strategies: int
    n_pairs: int
    n_defined_pairs: int
    n_undefined_pairs: int

    def to_dict(self) -> dict[str, object]:
        return {
            "n_strategies": self.n_strategies,
            "n_pairs": self.n_pairs,
            "n_defined_pairs": self.n_defined_pairs,
            "n_undefined_pairs": self.n_undefined_pairs,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> Coverage:
        return cls(
            n_strategies=_req_int(raw, "n_strategies"),
            n_pairs=_req_int(raw, "n_pairs"),
            n_defined_pairs=_req_int(raw, "n_defined_pairs"),
            n_undefined_pairs=_req_int(raw, "n_undefined_pairs"),
        )


@dataclass(frozen=True, slots=True)
class StrategyComparison:
    """A sealed, content-addressed strategy-comparison record (§9).

    Implements the :class:`~quantforge.factors.store.ResearchRecord` Protocol
    (:attr:`research_result_id` aliases :attr:`strategy_comparison_id`; deterministic
    :meth:`to_dict`), so it persists write-once to the shared research sidecar with no
    new store. It pins each strategy by ``(label, walk_forward_id, result_hash)`` in
    request order, records the shared schedule / producing engine version /
    annualization / risk-free conventions, holds the per-strategy summary block and the
    upper-triangle pairwise matrix, carries the referenced corpus pins, and seals the
    computed answer into ``result_hash``. It is **not** a ``Pit*`` type and exposes no
    as-of accessor (SC-6).
    """

    strategy_comparison_engine_version_id: str
    comparison_spec: dict[str, object]
    strategy_refs: tuple[tuple[str, str, str], ...]
    boundary_kind: str
    schedule_id: str
    factor_portfolio_engine_version_id: str
    periods_per_year: str
    risk_free_per_period: str
    trials: tuple[TrialSummary, ...]
    comparisons: tuple[ComparisonCell, ...]
    coverage: Coverage
    dataset_version_ids: tuple[str, ...]
    market_dataset_version_ids: tuple[str, ...]
    method_version: str
    result_hash: str

    # -- derived ids (never stored as state) ---------------------------------

    @property
    def strategy_comparison_id(self) -> str:
        """The content-addressed id - request, referenced content, **and** answer (§10).

        Re-derived from the record's own fields on every access (never read from stored
        state), so a tampered stored id is ignored and ``from_dict(to_dict(r))``
        re-emits an identical id. Folds the engine version, the spec identity (extracted
        from the embedded request), the ordered strategy ``result_hash``es, the shared
        ``periods_per_year``, and the sealed ``result_hash`` over the computed answer.
        """
        spec = self.comparison_spec
        return _strategy_comparison_id(
            strategy_comparison_engine_version_id=(
                self.strategy_comparison_engine_version_id
            ),
            name=_spec_str(spec, "name"),
            spec_version=_spec_str(spec, "spec_version"),
            walk_forward_ids=[ref[1] for ref in self.strategy_refs],
            strategy_result_hashes=[ref[2] for ref in self.strategy_refs],
            periods_per_year=self.periods_per_year,
            result_hash=self.result_hash,
        )

    @property
    def research_result_id(self) -> str:
        """Alias of :attr:`strategy_comparison_id` - the :class:`ResearchRecord` id."""
        return self.strategy_comparison_id

    @property
    def walk_forward_ids(self) -> tuple[str, ...]:
        """The referenced strategy ids, in request order (fixes labels + pair order)."""
        return tuple(ref[1] for ref in self.strategy_refs)

    @property
    def pin_mismatch(self) -> bool:
        """True iff the strategies differ on any carried corpus pin (§9).

        Surfaced, never raised (mirrors
        :attr:`~quantforge.campaign.result.ResearchCampaignEvaluation.pin_mismatch`): a
        comparison may legitimately evaluate strategies run over a different corpus
        snapshot, but a reader must be able to see that the references were not pinned
        identically. (Commensurability - one schedule, engine version, annualization,
        and risk-free convention - is a separate, *raised* contract.)
        """
        return (
            len(self.dataset_version_ids) > 1
            or len(self.market_dataset_version_ids) > 1
        )

    def cell(self, i: int, j: int) -> ComparisonCell:
        """The pairwise cell for the ordered pair ``(i, j)`` (SC-8, antisymmetry).

        Returns the stored upper-triangle cell for ``i < j``; for ``i > j`` returns its
        :meth:`~ComparisonCell.transpose` (sign-flipped mean/t/Sharpe, preserved
        p-value/overlap). ``i == j`` is a degenerate self-comparison and raises - the
        matrix has no diagonal. Indices out of range raise.
        """
        n = len(self.trials)
        if not (0 <= i < n and 0 <= j < n):
            raise IndexError(f"strategy index out of range for {n} strategies")
        if i == j:
            raise ValueError(
                "a strategy has no self-comparison cell (the matrix has no diagonal)"
            )
        lo, hi = (i, j) if i < j else (j, i)
        stored = self._upper[(lo, hi)]
        return stored if i < j else stored.transpose()

    @property
    def _upper(self) -> dict[tuple[int, int], ComparisonCell]:
        """The ``(i, j) -> cell`` lookup over the stored upper triangle."""
        return {(cell.i, cell.j): cell for cell in self.comparisons}

    # -- sealing --------------------------------------------------------------

    @classmethod
    def seal(
        cls,
        *,
        strategy_comparison_engine_version_id: str,
        comparison_spec: dict[str, object],
        strategy_refs: tuple[tuple[str, str, str], ...],
        boundary_kind: str,
        schedule_id: str,
        factor_portfolio_engine_version_id: str,
        periods_per_year: str,
        risk_free_per_period: str,
        trials: tuple[TrialSummary, ...],
        comparisons: tuple[ComparisonCell, ...],
        coverage: Coverage,
        dataset_version_ids: tuple[str, ...],
        market_dataset_version_ids: tuple[str, ...],
        method_version: str = COMPARISON_METHOD_VERSION,
    ) -> StrategyComparison:
        """Seal computed blocks, folding the answer into ``result_hash`` (§10).

        The single constructor the engine uses: it folds the ordered computed-output
        cells (the per-strategy summary cells in request order, then the upper-triangle
        pairwise cells) into ``result_hash`` via
        :func:`~quantforge.comparison.identity.strategy_comparison_result_hash`, so
        identity is a pure function of the computed answer and never has to be supplied
        by the caller. The coverage block is a function of those cells and is excluded.
        """
        rhash = _result_hash(_output_cells(trials=trials, comparisons=comparisons))
        return cls(
            strategy_comparison_engine_version_id=(
                strategy_comparison_engine_version_id
            ),
            comparison_spec=dict(comparison_spec),
            strategy_refs=strategy_refs,
            boundary_kind=boundary_kind,
            schedule_id=schedule_id,
            factor_portfolio_engine_version_id=factor_portfolio_engine_version_id,
            periods_per_year=periods_per_year,
            risk_free_per_period=risk_free_per_period,
            trials=trials,
            comparisons=comparisons,
            coverage=coverage,
            dataset_version_ids=dataset_version_ids,
            market_dataset_version_ids=market_dataset_version_ids,
            method_version=method_version,
            result_hash=rhash,
        )

    # -- serialization --------------------------------------------------------

    def to_dict(self) -> dict[str, object]:
        return {
            "strategy_comparison_id": self.strategy_comparison_id,
            # The ResearchRecord alias so the generic sidecar reader keys correctly.
            "research_result_id": self.research_result_id,
            "strategy_comparison_engine_version_id": (
                self.strategy_comparison_engine_version_id
            ),
            "comparison_spec": dict(self.comparison_spec),
            "strategy_refs": [
                {"label": label, "ref": [walk_forward_id, result_hash]}
                for label, walk_forward_id, result_hash in self.strategy_refs
            ],
            "boundary_kind": self.boundary_kind,
            "schedule_id": self.schedule_id,
            "factor_portfolio_engine_version_id": (
                self.factor_portfolio_engine_version_id
            ),
            "periods_per_year": self.periods_per_year,
            "risk_free_per_period": self.risk_free_per_period,
            "trials": [trial.to_dict() for trial in self.trials],
            "comparisons": [cell.to_dict() for cell in self.comparisons],
            "coverage": self.coverage.to_dict(),
            "dataset_version_ids": list(self.dataset_version_ids),
            "market_dataset_version_ids": list(self.market_dataset_version_ids),
            "method_version": self.method_version,
            "result_hash": self.result_hash,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> StrategyComparison:
        """Reconstruct a sealed comparison record from its :meth:`to_dict` payload.

        The additive inverse of :meth:`to_dict`, so a record read back from the shared
        sidecar via ``store.read_as(id, StrategyComparison.from_dict)`` is a first-class
        typed object. ``strategy_comparison_id`` / ``research_result_id`` are derived
        aliases re-emitted by their properties (never read from state), every nested
        cell round-trips through its own fail-closed ``from_dict``, and the block order
        is preserved - so ``from_dict(to_dict(r))`` re-emits identical bytes and the
        same ``result_hash``, introducing no drift.
        """
        return cls(
            strategy_comparison_engine_version_id=_req_str(
                raw, "strategy_comparison_engine_version_id"
            ),
            comparison_spec=dict(_req_dict(raw, "comparison_spec")),
            strategy_refs=_strategy_refs(_req_list(raw, "strategy_refs")),
            boundary_kind=_req_str(raw, "boundary_kind"),
            schedule_id=_req_str(raw, "schedule_id"),
            factor_portfolio_engine_version_id=_req_str(
                raw, "factor_portfolio_engine_version_id"
            ),
            periods_per_year=_req_str(raw, "periods_per_year"),
            risk_free_per_period=_req_str(raw, "risk_free_per_period"),
            trials=tuple(
                TrialSummary.from_dict(_as_dict(item, "trials"))
                for item in _req_list(raw, "trials")
            ),
            comparisons=tuple(
                ComparisonCell.from_dict(_as_dict(item, "comparisons"))
                for item in _req_list(raw, "comparisons")
            ),
            coverage=Coverage.from_dict(_req_dict(raw, "coverage")),
            dataset_version_ids=tuple(
                _as_str(item, "dataset_version_ids")
                for item in _req_list(raw, "dataset_version_ids")
            ),
            market_dataset_version_ids=tuple(
                _as_str(item, "market_dataset_version_ids")
                for item in _req_list(raw, "market_dataset_version_ids")
            ),
            method_version=_req_str(raw, "method_version"),
            result_hash=_req_str(raw, "result_hash"),
        )


def _negate(cell: StatValue) -> StatValue:
    """A KNOWN cell's arithmetic negation (canonical), or an UNDEFINED cell unchanged.

    Used by :meth:`ComparisonCell.transpose` for the antisymmetric statistics, so the
    ``(j, i)`` view reproduces exactly what a ``(j, i)`` computation would produce.
    The stored string already carries the pinned context's precision, so the sign flip
    must be **exact** - ``Decimal.copy_negate`` flips the sign without consulting (and
    thus without rounding to) the ambient decimal context, unlike unary ``-``, which
    would silently truncate the magnitude to the process-default precision. A negated
    zero is re-canonicalized to positive zero (``copy_abs``) so a zero mean/``t`` cell
    transposes to the same canonical string a reversed computation would seal, never
    ``"-0"``. An UNDEFINED cell has nothing to negate and passes through.
    """
    if cell.status is StatStatus.KNOWN:
        assert cell.value is not None  # guaranteed by a KNOWN StatValue
        flipped = Decimal(cell.value).copy_negate()
        if flipped.is_zero():
            flipped = flipped.copy_abs()
        return StatValue.known(str(flipped))
    assert cell.reason is not None  # guaranteed by an UNDEFINED StatValue
    return StatValue.undefined(cell.reason)


def _output_cells(
    *,
    trials: tuple[TrialSummary, ...],
    comparisons: tuple[ComparisonCell, ...],
) -> list[dict[str, object]]:
    """The ordered computed-output cells sealed into ``result_hash`` (§10).

    A single deterministic list - the per-strategy summary cells in request order, then
    the upper-triangle pairwise cells in their sealed order - each tagged by its block
    so two structurally different records can never collide, and each reduced to its
    canonical form. The derivable ``label_i`` / ``label_j`` are omitted from the
    pairwise cell (the ``i`` / ``j`` indices fold them); the ids, labels, carried pins,
    and shared conventions are folded into ``strategy_comparison_id`` through the
    request + reference instead. Sensitive to every computed statistic: one differing
    cell changes ``result_hash`` and therefore ``strategy_comparison_id``. The coverage
    block is a pure function of these cells and is excluded.
    """
    cells: list[dict[str, object]] = []
    for trial in trials:
        cells.append(
            {
                "block": "strategy",
                "label": trial.label,
                "sharpe": trial.sharpe.to_dict(),
                "n_valid_periods": trial.n_valid_periods,
                "axis_periods": trial.axis_periods,
            }
        )
    for pair in comparisons:
        cell: dict[str, object] = {
            "block": "pair",
            "i": pair.i,
            "j": pair.j,
            "status": pair.status.value,
            "overlap_periods": pair.overlap_periods,
            "mean_diff": pair.mean_diff.to_dict(),
            "stderr_diff": pair.stderr_diff.to_dict(),
            "t_stat": pair.t_stat.to_dict(),
            "p_value": pair.p_value.to_dict(),
            "sharpe_diff": pair.sharpe_diff.to_dict(),
        }
        if pair.reason is not None:
            cell["reason"] = pair.reason.value
        cells.append(cell)
    return cells


def _spec_str(spec: dict[str, object], key: str) -> str:
    """Read a required string field from the embedded request payload (fail closed)."""
    value = spec.get(key)
    if not isinstance(value, str):
        raise ValueError(f"comparison_spec.{key} must be a string")
    return value
