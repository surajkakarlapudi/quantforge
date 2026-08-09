"""The sealed, content-addressed performance-analytics record (proposal §J.2, §L).

A completed analytics computation is a :class:`PerformanceAnalytics`: the engine
version, the full declarative request, the ``(backtest_id, result_hash)`` reference to
the subject (and optionally the benchmark), the shared ``schedule_id`` and analysed
period count, the three computed statistic blocks (absolute / relative / VaR — each an
ordered tuple of UNDEFINED-preserving :class:`~quantforge.analytics.model.StatValue`
cells), the recorded annualization convention, the carried-through corpus pins, and the
sealed ``result_hash`` over the computed answer.

Like every research record in this project it satisfies the
:class:`~quantforge.factors.store.ResearchRecord` Protocol — ``research_result_id``
aliases ``analytics_id`` (a single id, mirroring ``BacktestResult.backtest_id``; D6) and
``to_dict`` is deterministic — so it persists write-once to the shared Phase 8 sidecar
with **no new store** (D1). It stores only *pointers* to the referenced backtests, never
a copy of their ledgers (the pointer-only discipline of
:class:`~quantforge.experiment.result.ExperimentResult`): the referenced results already
live in the same sidecar, so this record stays a thin, reproducible index over them.

Every value is deterministically serializable and round-trips byte-identically through
:meth:`~PerformanceAnalytics.from_dict`; the derived ids are re-emitted by their
properties, never read from stored state, so a tampered stored id is ignored and
``from_dict(to_dict(r))`` re-emits identical bytes. No wall-clock, RNG, or
iteration-order dependence enters any value or id.
"""

from __future__ import annotations

from dataclasses import dataclass

from quantforge.analytics.identity import analytics_id as _analytics_id
from quantforge.analytics.identity import analytics_result_hash as _result_hash
from quantforge.analytics.model import StatValue
from quantforge.analytics.version import ANALYTICS_FORMULA_VERSION

__all__ = [
    "ANALYTICS_RESULT_FORMAT_VERSION",
    "BOUNDARY_PIT",
    "PerformanceAnalytics",
]

#: The §9 record-schema version for the analytics record — distinct from the
#: engine-logic version, the formula version, and the sidecar's container format
#: version. Bump it when the serialized meaning of an analytics record changes (a
#: container concern; it is **not** folded into ``analytics_id`` — proposal §L, Phase 14
#: D9 discipline).
ANALYTICS_RESULT_FORMAT_VERSION = "analytics-result/1"

#: The only boundary a v1 analytics record accepts (proposal §M, inv. 27). Backtests are
#: PIT-only by construction, so their returns are PIT-only; the record carries this
#: explicit, un-defaulted value and the engine fails closed on anything else. A REVISED
#: analytics scope is reserved for a future explicitly-labelled phase (Phase 14 D10).
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


def _ref_pair(value: object, key: str) -> tuple[str, str]:
    """Decode a ``[id, content_hash]`` reference pair; fail closed otherwise."""
    if (
        not isinstance(value, list)
        or len(value) != 2
        or not all(isinstance(item, str) for item in value)
    ):
        raise ValueError(f"{key} must be an [id, content_hash] string pair")
    return (value[0], value[1])


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


def _var_cells(
    items: list[object],
) -> tuple[tuple[str, StatValue, StatValue], ...]:
    """Decode the VaR block into ``(confidence, var, cvar)`` triples."""
    out: list[tuple[str, StatValue, StatValue]] = []
    for item in items:
        raw = _as_dict(item, "var")
        confidence = raw.get("confidence")
        if not isinstance(confidence, str):
            raise ValueError("each var entry must carry a string confidence")
        var_cell = StatValue.from_dict(_req_dict(raw, "var"))
        cvar_cell = StatValue.from_dict(_req_dict(raw, "cvar"))
        out.append((confidence, var_cell, cvar_cell))
    return tuple(out)


@dataclass(frozen=True, slots=True)
class PerformanceAnalytics:
    """A sealed, content-addressed performance-analytics record (§J.2, D1, D6).

    Implements the :class:`~quantforge.factors.store.ResearchRecord` Protocol
    (:attr:`research_result_id` aliases :attr:`analytics_id`; deterministic
    :meth:`to_dict`), so it persists write-once to the shared research sidecar with no
    new store. It pins the subject and (optional) benchmark by ``(backtest_id,
    result_hash)``, records the shared schedule and analysed period count, holds the
    three computed statistic blocks and the annualization convention, carries the
    referenced corpus pins for audit, and seals the computed answer into ``result_hash``
    — so its identity is a pure function of the request, the referenced content, and the
    computed statistics.
    """

    analytics_engine_version_id: str
    analytics_spec: dict[str, object]
    subject_ref: tuple[str, str]
    benchmark_ref: tuple[str, str] | None
    boundary_kind: str
    schedule_id: str
    periods: int
    absolute: tuple[tuple[str, StatValue], ...]
    relative: tuple[tuple[str, StatValue], ...]
    var: tuple[tuple[str, StatValue, StatValue], ...]
    risk_free_per_period: str
    periods_per_year: str
    dataset_version_ids: tuple[str, ...]
    market_dataset_version_ids: tuple[str, ...]
    formula_version: str
    result_hash: str

    # -- derived ids (never stored as state) ---------------------------------

    @property
    def analytics_id(self) -> str:
        """The content-addressed id — request, referenced content, **and** answer (§L).

        Re-derived from the record's own fields on every access (never read from stored
        state), so a tampered stored id is ignored and ``from_dict(to_dict(r))``
        re-emits an identical id. Folds the engine version, the spec identity (extracted
        from the embedded request), both referenced ``result_hash``es, and the sealed
        ``result_hash`` over the computed answer.
        """
        spec = self.analytics_spec
        return _analytics_id(
            analytics_engine_version_id=self.analytics_engine_version_id,
            name=_spec_str(spec, "name"),
            spec_version=_spec_str(spec, "spec_version"),
            subject_id=self.subject_ref[0],
            benchmark_id=self.benchmark_ref[0] if self.benchmark_ref else None,
            sorted_var_confidences=_spec_confidences(spec),
            risk_free_per_period=self.risk_free_per_period,
            periods_per_year=self.periods_per_year,
            subject_result_hash=self.subject_ref[1],
            benchmark_result_hash=(
                self.benchmark_ref[1] if self.benchmark_ref else None
            ),
            result_hash=self.result_hash,
        )

    @property
    def research_result_id(self) -> str:
        """Alias of :attr:`analytics_id` — the :class:`ResearchRecord` identity (D6)."""
        return self.analytics_id

    @property
    def pin_mismatch(self) -> bool:
        """True iff subject and benchmark differ on any carried corpus pin (§N).

        Surfaced, never raised (mirrors ``UniverseComparison.mode_mismatch`` / Phase 13
        ``pin_mismatch``): a record may legitimately compare a strategy to a benchmark
        run over a different corpus snapshot, but a reader must be able to see that the
        two were not pinned identically. ``False`` for an absolute-only (benchmark-free)
        record — there is nothing to disagree with. A record is flagged when more than
        one distinct pin appears in either the fundamentals or the market dimension.
        """
        if self.benchmark_ref is None:
            return False
        return (
            len(self.dataset_version_ids) > 1
            or len(self.market_dataset_version_ids) > 1
        )

    # -- sealing --------------------------------------------------------------

    @classmethod
    def seal(
        cls,
        *,
        analytics_engine_version_id: str,
        analytics_spec: dict[str, object],
        subject_ref: tuple[str, str],
        benchmark_ref: tuple[str, str] | None,
        boundary_kind: str,
        schedule_id: str,
        periods: int,
        absolute: tuple[tuple[str, StatValue], ...],
        relative: tuple[tuple[str, StatValue], ...],
        var: tuple[tuple[str, StatValue, StatValue], ...],
        risk_free_per_period: str,
        periods_per_year: str,
        dataset_version_ids: tuple[str, ...],
        market_dataset_version_ids: tuple[str, ...],
        formula_version: str = ANALYTICS_FORMULA_VERSION,
    ) -> PerformanceAnalytics:
        """Seal computed statistic blocks, folding the answer into ``result_hash`` (§L).

        The single constructor the engine uses: it folds the ordered computed-output
        cells (absolute, then relative, then VaR) into ``result_hash`` via
        :func:`~quantforge.analytics.identity.analytics_result_hash`, so identity is a
        pure function of the computed answer and never has to be supplied by the caller.
        """
        rhash = _result_hash(
            _output_cells(absolute=absolute, relative=relative, var=var)
        )
        return cls(
            analytics_engine_version_id=analytics_engine_version_id,
            analytics_spec=dict(analytics_spec),
            subject_ref=subject_ref,
            benchmark_ref=benchmark_ref,
            boundary_kind=boundary_kind,
            schedule_id=schedule_id,
            periods=periods,
            absolute=absolute,
            relative=relative,
            var=var,
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
            "analytics_id": self.analytics_id,
            # The ResearchRecord alias so the generic sidecar reader keys correctly.
            "research_result_id": self.research_result_id,
            "analytics_engine_version_id": self.analytics_engine_version_id,
            "analytics_spec": dict(self.analytics_spec),
            "subject_ref": list(self.subject_ref),
            "benchmark_ref": (
                list(self.benchmark_ref) if self.benchmark_ref is not None else None
            ),
            "boundary_kind": self.boundary_kind,
            "schedule_id": self.schedule_id,
            "periods": self.periods,
            "absolute": [{"key": key, **cell.to_dict()} for key, cell in self.absolute],
            "relative": [{"key": key, **cell.to_dict()} for key, cell in self.relative],
            "var": [
                {
                    "confidence": confidence,
                    "var": var_cell.to_dict(),
                    "cvar": cvar_cell.to_dict(),
                }
                for confidence, var_cell, cvar_cell in self.var
            ],
            "risk_free_per_period": self.risk_free_per_period,
            "periods_per_year": self.periods_per_year,
            "dataset_version_ids": list(self.dataset_version_ids),
            "market_dataset_version_ids": list(self.market_dataset_version_ids),
            "formula_version": self.formula_version,
            "result_hash": self.result_hash,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> PerformanceAnalytics:
        """Reconstruct a sealed analytics record from its :meth:`to_dict` payload.

        The additive inverse of :meth:`to_dict`, so a record read back from the shared
        sidecar via ``store.read_as(id, PerformanceAnalytics.from_dict)`` is a
        first-class typed object. ``analytics_id`` / ``research_result_id`` are derived
        aliases re-emitted by their properties (never read from state), every
        ``StatValue`` cell round-trips through its own fail-closed ``from_dict``, and
        the block order is preserved — so ``from_dict(to_dict(r))`` re-emits identical
        bytes and the same ``result_hash``, introducing no drift.
        """
        benchmark_raw = raw.get("benchmark_ref")
        benchmark_ref = (
            None if benchmark_raw is None else _ref_pair(benchmark_raw, "benchmark_ref")
        )
        return cls(
            analytics_engine_version_id=_req_str(raw, "analytics_engine_version_id"),
            analytics_spec=dict(_req_dict(raw, "analytics_spec")),
            subject_ref=_ref_pair(raw["subject_ref"], "subject_ref"),
            benchmark_ref=benchmark_ref,
            boundary_kind=_req_str(raw, "boundary_kind"),
            schedule_id=_req_str(raw, "schedule_id"),
            periods=_req_int(raw, "periods"),
            absolute=_keyed_cells(_req_list(raw, "absolute"), "absolute"),
            relative=_keyed_cells(_req_list(raw, "relative"), "relative"),
            var=_var_cells(_req_list(raw, "var")),
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
    absolute: tuple[tuple[str, StatValue], ...],
    relative: tuple[tuple[str, StatValue], ...],
    var: tuple[tuple[str, StatValue, StatValue], ...],
) -> list[dict[str, object]]:
    """The ordered computed-output cells sealed into ``result_hash`` (§L).

    A single deterministic list — absolute, then relative, then VaR — each cell tagged
    by its block so two structurally different records can never collide, and each
    reduced to its canonical ``StatValue`` form. Sensitive to every computed statistic:
    one differing cell changes ``result_hash`` and therefore ``analytics_id``.
    """
    cells: list[dict[str, object]] = []
    for key, cell in absolute:
        cells.append({"block": "absolute", "key": key, **cell.to_dict()})
    for key, cell in relative:
        cells.append({"block": "relative", "key": key, **cell.to_dict()})
    for confidence, var_cell, cvar_cell in var:
        cells.append(
            {
                "block": "var",
                "confidence": confidence,
                "var": var_cell.to_dict(),
                "cvar": cvar_cell.to_dict(),
            }
        )
    return cells


def _as_str(value: object, key: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"each {key} entry must be a string")
    return value


def _spec_str(spec: dict[str, object], key: str) -> str:
    """Read a required string field from the embedded request payload (fail closed)."""
    value = spec.get(key)
    if not isinstance(value, str):
        raise ValueError(f"analytics_spec.{key} must be a string")
    return value


def _spec_confidences(spec: dict[str, object]) -> list[str]:
    """Read the sorted VaR confidences out of the embedded request (fail closed).

    The embedded ``AnalyticsSpecification.to_dict()`` already emits ``var_confidences``
    in its sorted, canonical form, so the value folded into ``analytics_id`` is
    order-independent by construction.
    """
    value = spec.get("var_confidences")
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ValueError("analytics_spec.var_confidences must be a list of strings")
    return list(value)
