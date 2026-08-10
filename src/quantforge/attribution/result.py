"""The sealed, content-addressed factor-attribution record (proposal §9, §8).

A completed attribution computation is a :class:`FactorAttribution`: the engine version,
the full declarative request, the ``(backtest_id, result_hash)`` reference to the
subject and to each factor (in request order), the shared ``schedule_id`` and analysed
period count, the three computed blocks (coefficients / diagnostics / decomposition —
each an ordered tuple of UNDEFINED-preserving
:class:`~quantforge.attribution.model.StatValue` cells), the residual **digest** (D4 —
the digest only, never the residual series), the recorded annualization convention, the
carried-through corpus pins, and the sealed ``result_hash`` over the computed answer.

Like every research record in this project it satisfies the
:class:`~quantforge.factors.store.ResearchRecord` Protocol — ``research_result_id``
aliases ``attribution_id`` (a single id, mirroring ``analytics_id`` /
``BacktestResult.backtest_id``; D2) and ``to_dict`` is deterministic — so it persists
write-once to the shared Phase 8 sidecar with **no new store** (§10). It stores only
*pointers* to the referenced backtests, never a copy of their ledgers or return vectors
(the pointer-only discipline of
:class:`~quantforge.analytics.result.PerformanceAnalytics`): the referenced results
already live in the same sidecar, so this record stays a thin, reproducible index over
them.

**Ex-post, not PIT (FA-2).** A regression of realized returns is an ex-post research
statistic, not a forward-usable PIT value. :class:`FactorAttribution` is deliberately
**not** a ``Pit*`` type and exposes **no** as-of accessor: it can never be handed to a
layer that requires a PIT signal. ``boundary_kind = "pit"`` documents only that the
*underlying backtests were PIT walks* — the Phase 16 SD-2 convention where the label
describes the input side, not the ex-post output.

Every value is deterministically serializable and round-trips byte-identically through
:meth:`~FactorAttribution.from_dict`; the derived ids are re-emitted by their
properties, never read from stored state, so a tampered stored id is ignored and
``from_dict(to_dict(r))`` re-emits identical bytes. No wall-clock, RNG, or
iteration-order dependence enters any value or id.
"""

from __future__ import annotations

from dataclasses import dataclass

from quantforge.attribution.identity import attribution_id as _attribution_id
from quantforge.attribution.identity import attribution_result_hash as _result_hash
from quantforge.attribution.model import StatValue
from quantforge.attribution.version import ATTRIBUTION_FORMULA_VERSION

__all__ = [
    "ATTRIBUTION_RESULT_FORMAT_VERSION",
    "BOUNDARY_PIT",
    "FactorAttribution",
]

#: The §9 record-schema version for the attribution record — distinct from the
#: engine-logic version, the formula version, and the sidecar's container format
#: version. Bump it when the serialized meaning of an attribution record changes (a
#: container concern; it is **not** folded into ``attribution_id`` — proposal §8, Phase
#: 14/15 D-discipline).
ATTRIBUTION_RESULT_FORMAT_VERSION = "attribution-result/1"

#: The only boundary a v1 attribution record accepts (proposal §7, inv. 27/28).
#: Backtests
#: are PIT-only by construction, so their returns are PIT-only; the record carries this
#: explicit, un-defaulted value and the engine sets it unconditionally. It documents the
#: *input* side (the underlying backtests were PIT walks); the attribution *output* is
#: ex-post and is not a PIT value (FA-2). A REVISED attribution scope is reserved for a
#: future explicitly-labelled phase.
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


def _ref_pair(value: object, key: str) -> tuple[str, str]:
    """Decode a ``[id, content_hash]`` reference pair; fail closed otherwise."""
    if (
        not isinstance(value, list)
        or len(value) != 2
        or not all(isinstance(item, str) for item in value)
    ):
        raise ValueError(f"{key} must be an [id, content_hash] string pair")
    return (value[0], value[1])


def _factor_refs(items: list[object]) -> tuple[tuple[str, str, str], ...]:
    """Decode the ordered factor references into ``(label, id, content_hash)``
    triples."""
    out: list[tuple[str, str, str]] = []
    for item in items:
        raw = _as_dict(item, "factor_refs")
        label = raw.get("label")
        if not isinstance(label, str):
            raise ValueError("each factor_refs entry must carry a string label")
        id_hash = _ref_pair(raw.get("ref"), "factor_refs.ref")
        out.append((label, id_hash[0], id_hash[1]))
    return tuple(out)


def _keyed_cells(items: list[object], key: str) -> tuple[tuple[str, StatValue], ...]:
    """Decode a ``[{"key", <cell>}, ...]`` block into ``(key, StatValue)`` pairs."""
    out: list[tuple[str, StatValue]] = []
    for item in items:
        raw = _as_dict(item, key)
        stat_key = raw.get("key")
        if not isinstance(stat_key, str):
            raise ValueError(f"each {key} entry must carry a string key")
        out.append((stat_key, StatValue.from_dict(raw)))
    return tuple(out)


def _coefficient_cells(
    items: list[object],
) -> tuple[tuple[str, StatValue, StatValue, StatValue], ...]:
    """Decode the coefficient block into ``(label, estimate, std_error, t_stat)``."""
    out: list[tuple[str, StatValue, StatValue, StatValue]] = []
    for item in items:
        raw = _as_dict(item, "coefficients")
        label = raw.get("label")
        if not isinstance(label, str):
            raise ValueError("each coefficient entry must carry a string label")
        estimate = StatValue.from_dict(_req_dict(raw, "estimate"))
        std_error = StatValue.from_dict(_req_dict(raw, "std_error"))
        t_stat = StatValue.from_dict(_req_dict(raw, "t_stat"))
        out.append((label, estimate, std_error, t_stat))
    return tuple(out)


@dataclass(frozen=True, slots=True)
class FactorAttribution:
    """A sealed, content-addressed multi-factor attribution record (§9, D1, D2).

    Implements the :class:`~quantforge.factors.store.ResearchRecord` Protocol
    (:attr:`research_result_id` aliases :attr:`attribution_id`; deterministic
    :meth:`to_dict`), so it persists write-once to the shared research sidecar with no
    new store. It pins the subject and each factor by ``(backtest_id, result_hash)``,
    records the shared schedule and analysed period count, holds the three computed
    blocks (coefficients / diagnostics / decomposition) and the residual digest, carries
    the referenced corpus pins for audit, and seals the computed answer into
    ``result_hash`` — so its identity is a pure function of the request, the referenced
    content, and the computed statistics. It is **not** a ``Pit*`` type and exposes no
    as-of accessor (FA-2).
    """

    attribution_engine_version_id: str
    attribution_spec: dict[str, object]
    subject_ref: tuple[str, str]
    factor_refs: tuple[tuple[str, str, str], ...]
    boundary_kind: str
    schedule_id: str
    periods: int
    coefficients: tuple[tuple[str, StatValue, StatValue, StatValue], ...]
    diagnostics: tuple[tuple[str, StatValue], ...]
    decomposition: tuple[tuple[str, StatValue], ...]
    residual_digest: str
    risk_free_per_period: str
    periods_per_year: str
    dataset_version_ids: tuple[str, ...]
    market_dataset_version_ids: tuple[str, ...]
    formula_version: str
    result_hash: str

    # -- derived ids (never stored as state) ---------------------------------

    @property
    def attribution_id(self) -> str:
        """The content-addressed id — request, referenced content, **and** answer (§8).

        Re-derived from the record's own fields on every access (never read from stored
        state), so a tampered stored id is ignored and ``from_dict(to_dict(r))``
        re-emits an identical id. Folds the engine version, the spec identity (extracted
        from the embedded request), the subject and ordered factor ``result_hash``es,
        and the sealed ``result_hash`` over the computed answer.
        """
        spec = self.attribution_spec
        return _attribution_id(
            attribution_engine_version_id=self.attribution_engine_version_id,
            name=_spec_str(spec, "name"),
            spec_version=_spec_str(spec, "spec_version"),
            subject_id=self.subject_ref[0],
            factor_ids=[ref[1] for ref in self.factor_refs],
            risk_free_per_period=self.risk_free_per_period,
            periods_per_year=self.periods_per_year,
            subject_result_hash=self.subject_ref[1],
            factor_result_hashes=[ref[2] for ref in self.factor_refs],
            result_hash=self.result_hash,
        )

    @property
    def research_result_id(self) -> str:
        """Alias of :attr:`attribution_id` — the :class:`ResearchRecord` identity
        (D2)."""
        return self.attribution_id

    @property
    def pin_mismatch(self) -> bool:
        """True iff the subject and factors differ on any carried corpus pin (§9, FA-1).

        Surfaced, never raised (mirrors ``PerformanceAnalytics.pin_mismatch``): a record
        may legitimately regress a strategy against factors run over a different corpus
        snapshot, but a reader must be able to see that the references were not pinned
        identically. A record is flagged when more than one distinct pin appears in
        either the fundamentals or the market dimension.
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
        attribution_engine_version_id: str,
        attribution_spec: dict[str, object],
        subject_ref: tuple[str, str],
        factor_refs: tuple[tuple[str, str, str], ...],
        boundary_kind: str,
        schedule_id: str,
        periods: int,
        coefficients: tuple[tuple[str, StatValue, StatValue, StatValue], ...],
        diagnostics: tuple[tuple[str, StatValue], ...],
        decomposition: tuple[tuple[str, StatValue], ...],
        residual_digest: str,
        risk_free_per_period: str,
        periods_per_year: str,
        dataset_version_ids: tuple[str, ...],
        market_dataset_version_ids: tuple[str, ...],
        formula_version: str = ATTRIBUTION_FORMULA_VERSION,
    ) -> FactorAttribution:
        """Seal computed blocks, folding the answer into ``result_hash`` (§8).

        The single constructor the engine uses: it folds the ordered computed-output
        cells (coefficients, then diagnostics, then decomposition, then the residual
        digest) into ``result_hash`` via
        :func:`~quantforge.attribution.identity.attribution_result_hash`, so identity is
        a pure function of the computed answer and never has to be supplied by the
        caller.
        """
        rhash = _result_hash(
            _output_cells(
                coefficients=coefficients,
                diagnostics=diagnostics,
                decomposition=decomposition,
                residual_digest=residual_digest,
            )
        )
        return cls(
            attribution_engine_version_id=attribution_engine_version_id,
            attribution_spec=dict(attribution_spec),
            subject_ref=subject_ref,
            factor_refs=factor_refs,
            boundary_kind=boundary_kind,
            schedule_id=schedule_id,
            periods=periods,
            coefficients=coefficients,
            diagnostics=diagnostics,
            decomposition=decomposition,
            residual_digest=residual_digest,
            risk_free_per_period=risk_free_per_period,
            periods_per_year=periods_per_year,
            dataset_version_ids=dataset_version_ids,
            market_dataset_version_ids=market_dataset_version_ids,
            formula_version=formula_version,
            result_hash=rhash,
        )

    # -- serialization --------------------------------------------------------

    def to_dict(self) -> dict[str, object]:
        return {
            "attribution_id": self.attribution_id,
            # The ResearchRecord alias so the generic sidecar reader keys correctly.
            "research_result_id": self.research_result_id,
            "attribution_engine_version_id": self.attribution_engine_version_id,
            "attribution_spec": dict(self.attribution_spec),
            "subject_ref": list(self.subject_ref),
            "factor_refs": [
                {"label": label, "ref": [backtest_id, result_hash]}
                for label, backtest_id, result_hash in self.factor_refs
            ],
            "boundary_kind": self.boundary_kind,
            "schedule_id": self.schedule_id,
            "periods": self.periods,
            "coefficients": [
                {
                    "label": label,
                    "estimate": estimate.to_dict(),
                    "std_error": std_error.to_dict(),
                    "t_stat": t_stat.to_dict(),
                }
                for label, estimate, std_error, t_stat in self.coefficients
            ],
            "diagnostics": [
                {"key": key, **cell.to_dict()} for key, cell in self.diagnostics
            ],
            "decomposition": [
                {"key": key, **cell.to_dict()} for key, cell in self.decomposition
            ],
            "residual_digest": self.residual_digest,
            "risk_free_per_period": self.risk_free_per_period,
            "periods_per_year": self.periods_per_year,
            "dataset_version_ids": list(self.dataset_version_ids),
            "market_dataset_version_ids": list(self.market_dataset_version_ids),
            "formula_version": self.formula_version,
            "result_hash": self.result_hash,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> FactorAttribution:
        """Reconstruct a sealed attribution record from its :meth:`to_dict` payload.

        The additive inverse of :meth:`to_dict`, so a record read back from the shared
        sidecar via ``store.read_as(id, FactorAttribution.from_dict)`` is a first-class
        typed object. ``attribution_id`` / ``research_result_id`` are derived aliases
        re-emitted by their properties (never read from state), every ``StatValue`` cell
        round-trips through its own fail-closed ``from_dict``, and the block order is
        preserved — so ``from_dict(to_dict(r))`` re-emits identical bytes and the same
        ``result_hash``, introducing no drift.
        """
        return cls(
            attribution_engine_version_id=_req_str(
                raw, "attribution_engine_version_id"
            ),
            attribution_spec=dict(_req_dict(raw, "attribution_spec")),
            subject_ref=_ref_pair(raw["subject_ref"], "subject_ref"),
            factor_refs=_factor_refs(_req_list(raw, "factor_refs")),
            boundary_kind=_req_str(raw, "boundary_kind"),
            schedule_id=_req_str(raw, "schedule_id"),
            periods=_req_int(raw, "periods"),
            coefficients=_coefficient_cells(_req_list(raw, "coefficients")),
            diagnostics=_keyed_cells(_req_list(raw, "diagnostics"), "diagnostics"),
            decomposition=_keyed_cells(
                _req_list(raw, "decomposition"), "decomposition"
            ),
            residual_digest=_req_str(raw, "residual_digest"),
            risk_free_per_period=_req_str(raw, "risk_free_per_period"),
            periods_per_year=_req_str(raw, "periods_per_year"),
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
    coefficients: tuple[tuple[str, StatValue, StatValue, StatValue], ...],
    diagnostics: tuple[tuple[str, StatValue], ...],
    decomposition: tuple[tuple[str, StatValue], ...],
    residual_digest: str,
) -> list[dict[str, object]]:
    """The ordered computed-output cells sealed into ``result_hash`` (§8).

    A single deterministic list — coefficients, then diagnostics, then decomposition,
    then the residual-digest cell — each cell tagged by its block so two structurally
    different records can never collide, and each reduced to its canonical form.
    Sensitive to every computed statistic and to the residual digest: one differing cell
    changes ``result_hash`` and therefore ``attribution_id``.
    """
    cells: list[dict[str, object]] = []
    for label, estimate, std_error, t_stat in coefficients:
        cells.append(
            {
                "block": "coefficients",
                "label": label,
                "estimate": estimate.to_dict(),
                "std_error": std_error.to_dict(),
                "t_stat": t_stat.to_dict(),
            }
        )
    for key, cell in diagnostics:
        cells.append({"block": "diagnostics", "key": key, **cell.to_dict()})
    for key, cell in decomposition:
        cells.append({"block": "decomposition", "key": key, **cell.to_dict()})
    cells.append({"block": "residual", "digest": residual_digest})
    return cells


def _spec_str(spec: dict[str, object], key: str) -> str:
    """Read a required string field from the embedded request payload (fail closed)."""
    value = spec.get(key)
    if not isinstance(value, str):
        raise ValueError(f"attribution_spec.{key} must be a string")
    return value
