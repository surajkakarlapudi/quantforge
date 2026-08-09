"""The sealed, content-addressed experiment result & its run ledger (locked §3.3, §4).

A completed experiment is an :class:`ExperimentResult`: the experiment identity, the
run convention, the two inherited corpus pins (locked D2), and the ordered
:class:`ExperimentRun` ledger — one entry per swept coordinate, each naming the sweep
coordinate and the sealed child ``backtest_id`` it produced. Like every research record
in this project it satisfies the :class:`~quantforge.factors.store.ResearchRecord`
Protocol (``research_result_id`` aliases the experiment result id; deterministic
``to_dict``), so it persists write-once to the shared Phase 8 sidecar with **no new
store** (locked D4).

The ledger deliberately stores only the *pointer* to each child result — the
``backtest_id`` — never a copy of the child's ledger. A child
:class:`~quantforge.backtest.result.BacktestResult` already lives in the same sidecar
(the engine sealed it there), so the experiment record stays a thin, reproducible index
into already-sealed, PIT-correct Phase 12 results (locked §1). ``result_hash`` seals the
ordered ``(coordinate, backtest_id)`` digests, so the experiment id pins both the
request and every child it produced: a single differing child changes the whole
experiment identity, honestly.

Every value is deterministically serializable and round-trips byte-identically through
its own ``from_dict`` (fail-closed decode, mirroring
:mod:`quantforge.backtest.result`); no wall-clock, RNG, or iteration-order dependence
enters any value or id.
"""

from __future__ import annotations

from dataclasses import dataclass

from quantforge.experiment.identity import experiment_result_hash as _result_hash
from quantforge.experiment.identity import experiment_result_id as _experiment_result_id

__all__ = [
    "EXPERIMENT_RESULT_FORMAT_VERSION",
    "ExperimentResult",
    "ExperimentRun",
]

#: The §9 record-schema version for the experiment record — distinct from the engine
#: logic version and from the sidecar's container format version. Bump it when the
#: serialized meaning of an experiment record changes.
EXPERIMENT_RESULT_FORMAT_VERSION = "experiment-result/1"


def _req_str(raw: dict[str, object], key: str) -> str:
    """Read a required string from a decoded payload; fail closed otherwise."""
    value = raw[key]
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string")
    return value


def _req_list(raw: dict[str, object], key: str) -> list[object]:
    value = raw[key]
    if not isinstance(value, list):
        raise ValueError(f"{key} must be a list")
    return value


def _req_dict(raw: dict[str, object], key: str) -> dict[str, object]:
    value = raw[key]
    if not isinstance(value, dict):
        raise ValueError(f"{key} must be an object")
    return value


@dataclass(frozen=True, slots=True)
class ExperimentRun:
    """One swept coordinate and the sealed child ``backtest_id`` it produced (§3.3).

    ``coordinate`` is the ``parameter``-sorted tuple of ``(parameter, canonical-value)``
    pairs identifying this point in the sweep — exactly the coordinate
    :meth:`~quantforge.experiment.spec.ExperimentSpecification.expand` emits, so a run
    is self-describing (which axis values it holds) without re-deriving the child spec.
    ``backtest_id`` is the content-addressed id of the sealed
    :class:`~quantforge.backtest.result.BacktestResult` — the pointer into the shared
    sidecar, never a copy of the child ledger.
    """

    coordinate: tuple[tuple[str, str], ...]
    backtest_id: str

    def digest(self) -> dict[str, object]:
        """The ``(coordinate, backtest_id)`` fingerprint sealed into ``result_hash``.

        Because ``backtest_id`` already folds the child's ``result_hash`` (D6), sealing
        the child id is equivalent to sealing the child's whole sealed output — the
        experiment identity is sensitive to any child that changes.
        """
        return {
            "coordinate": [list(pair) for pair in self.coordinate],
            "backtest_id": self.backtest_id,
        }

    def to_dict(self) -> dict[str, object]:
        return {
            "coordinate": [list(pair) for pair in self.coordinate],
            "backtest_id": self.backtest_id,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> ExperimentRun:
        """Reconstruct from a :meth:`to_dict` payload, coordinate order preserved.

        Each coordinate entry must be a ``[parameter, canonical-value]`` string pair;
        the stored order is authoritative (it is ``parameter``-sorted at construction),
        so a re-emitted :meth:`to_dict` is byte-identical.
        """
        pairs: list[tuple[str, str]] = []
        for pair in _req_list(raw, "coordinate"):
            if (
                not isinstance(pair, list)
                or len(pair) != 2
                or not all(isinstance(item, str) for item in pair)
            ):
                raise ValueError(
                    "each coordinate must be a [parameter, value] string pair"
                )
            pairs.append((pair[0], pair[1]))
        return cls(
            coordinate=tuple(pairs),
            backtest_id=_req_str(raw, "backtest_id"),
        )


@dataclass(frozen=True, slots=True)
class ExperimentResult:
    """A complete, sealed, content-addressed experiment (locked §3.3, §4, D4).

    Implements the :class:`~quantforge.factors.store.ResearchRecord` Protocol
    (:attr:`research_result_id` aliases :attr:`experiment_result_id`; deterministic
    :meth:`to_dict`), so it persists write-once to the shared research sidecar with no
    new store. It records the experiment identity, the engine version, the exact base
    request (``base_backtest_request`` — which itself pins both corpus snapshots), the
    sorted axis ids, the run convention threaded to every child (locked D5), the two
    inherited corpus pins surfaced for comparability checks (locked D2), the sealed
    ``result_hash`` over the ordered run digests, and the full :class:`ExperimentRun`
    ledger (one pointer per swept coordinate).
    """

    experiment_id: str
    experiment_engine_version_id: str
    base_backtest_request: dict[str, object]
    axis_ids: tuple[str, ...]
    runs: tuple[ExperimentRun, ...]
    risk_free_per_period: str
    periods_per_year: str
    dataset_version_id: str
    market_dataset_version_id: str
    result_hash: str

    @property
    def experiment_result_id(self) -> str:
        """The content-addressed sidecar key: ``sha256`` of id+engine+result_hash."""
        return _experiment_result_id(
            experiment_id=self.experiment_id,
            experiment_engine_version_id=self.experiment_engine_version_id,
            result_hash=self.result_hash,
        )

    @property
    def research_result_id(self) -> str:
        """Alias of :attr:`experiment_result_id` — the ``ResearchRecord`` identity."""
        return self.experiment_result_id

    @property
    def backtest_ids(self) -> tuple[str, ...]:
        """The child ``backtest_id``s in swept-coordinate order (the run pointers)."""
        return tuple(run.backtest_id for run in self.runs)

    @classmethod
    def seal(
        cls,
        *,
        experiment_id: str,
        experiment_engine_version_id: str,
        base_backtest_request: dict[str, object],
        axis_ids: tuple[str, ...],
        runs: tuple[ExperimentRun, ...],
        risk_free_per_period: str,
        periods_per_year: str,
        dataset_version_id: str,
        market_dataset_version_id: str,
    ) -> ExperimentResult:
        """Seal a completed run ledger, computing ``result_hash`` over the digests (§4).

        The single constructor the engine uses: it folds the ordered
        ``(coordinate, backtest_id)`` digests into ``result_hash``, so identity is a
        pure function of the sealed children and never has to be supplied by the caller.
        """
        rhash = _result_hash([run.digest() for run in runs])
        return cls(
            experiment_id=experiment_id,
            experiment_engine_version_id=experiment_engine_version_id,
            base_backtest_request=base_backtest_request,
            axis_ids=axis_ids,
            runs=runs,
            risk_free_per_period=risk_free_per_period,
            periods_per_year=periods_per_year,
            dataset_version_id=dataset_version_id,
            market_dataset_version_id=market_dataset_version_id,
            result_hash=rhash,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "experiment_result_id": self.experiment_result_id,
            # The ResearchRecord alias so the generic sidecar reader keys correctly.
            "research_result_id": self.research_result_id,
            "experiment_id": self.experiment_id,
            "experiment_engine_version_id": self.experiment_engine_version_id,
            "base_backtest_request": dict(self.base_backtest_request),
            "axis_ids": list(self.axis_ids),
            "runs": [run.to_dict() for run in self.runs],
            "risk_free_per_period": self.risk_free_per_period,
            "periods_per_year": self.periods_per_year,
            "dataset_version_id": self.dataset_version_id,
            "market_dataset_version_id": self.market_dataset_version_id,
            "result_hash": self.result_hash,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> ExperimentResult:
        """Reconstruct a sealed experiment from its :meth:`to_dict` payload.

        The additive inverse of :meth:`to_dict`, so an experiment read back from the
        shared sidecar via ``store.read_as(id, ExperimentResult.from_dict)`` is a
        first-class typed object. ``experiment_result_id`` / ``research_result_id`` are
        derived aliases re-emitted by their properties (not stored as state), and the
        run ledger round-trips in stored order — so ``from_dict(to_dict(r))`` re-emits
        an identical ``to_dict`` and the same ``result_hash``, introducing no drift.
        """
        return cls(
            experiment_id=_req_str(raw, "experiment_id"),
            experiment_engine_version_id=_req_str(raw, "experiment_engine_version_id"),
            base_backtest_request=dict(_req_dict(raw, "base_backtest_request")),
            axis_ids=tuple(
                _as_str(item, "axis_ids") for item in _req_list(raw, "axis_ids")
            ),
            runs=tuple(
                ExperimentRun.from_dict(_as_dict(item, "runs"))
                for item in _req_list(raw, "runs")
            ),
            risk_free_per_period=_req_str(raw, "risk_free_per_period"),
            periods_per_year=_req_str(raw, "periods_per_year"),
            dataset_version_id=_req_str(raw, "dataset_version_id"),
            market_dataset_version_id=_req_str(raw, "market_dataset_version_id"),
            result_hash=_req_str(raw, "result_hash"),
        )


def _as_str(value: object, key: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"each {key} entry must be a string")
    return value


def _as_dict(value: object, key: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"each {key} entry must be an object")
    return value
