"""The content-addressed identities for the comparative-research layer (locked §4).

Every identity here follows the project's §11 discipline verbatim — ``sha256:``
prefixed, ``_SEP = "\\x00"`` NUL-joined components, canonical JSON
(``sort_keys=True, ensure_ascii=False, separators=(",",":")``) for any structured
payload, and **no** dependence on the wall clock, a random value, an object ``id()``,
or iteration order. Re-declaring the identical request reproduces every id, on any
machine — the identical construction Phase 12's :mod:`quantforge.backtest.identity`
uses, with fresh domain tags so a Phase 13 id can never collide with a lower-layer one.

The ids, and what each pins (locked §4):

    sweep_axis_id          = sha256( domain "sweep-axis/1", parameter,
                                     canonical JSON of the *sorted* canonical values )
                             — a *set* identity: axis-value order never changes it.
    experiment_id          = sha256( domain "experiment/1", name, spec_version,
                                     base-request identity, sorted sweep_axis_ids,
                                     risk_free_per_period, periods_per_year )
    experiment_result_hash = sha256( canonical JSON of the ordered
                                     (coordinate, backtest_id) digests )
    experiment_result_id   = sha256( experiment_id, experiment_engine_version_id,
                                     experiment_result_hash )
    comparison_id          = sha256( domain "backtest-comparison/1",
                                     comparison_version_id, statistic_key, order,
                                     sorted member backtest_ids )
    experiment_engine_version_id = sha256( domain "experiment-engine/1" )
    comparison_version_id        = sha256( domain "backtest-comparison/1" )

``experiment_id`` folds every input that can materially change the experiment: its
name, the exact base request, every axis (as a sorted set), and the annualization run
convention threaded to every child (locked D5 — it changes each child's ``backtest_id``
and the reported Sharpe). Omitting any one would let two materially different
experiments share an id — dishonest content-addressing, rejected here.
"""

from __future__ import annotations

import json

from quantforge.sec.artifacts import sha256_hex

__all__ = [
    "comparison_id",
    "comparison_version_id",
    "experiment_engine_version_id",
    "experiment_id",
    "experiment_result_hash",
    "experiment_result_id",
    "sweep_axis_id",
]

# The NUL separator shared across every id space in the project (data-model §11); it
# cannot occur in a hash, a parameter name, a canonical-JSON payload, or a decimal
# string, so a joined payload is unambiguous.
_SEP = "\x00"

# Domain tags. A new tag (or a bump) yields distinct ids without altering any
# already-computed id — the extensibility discipline shared with every prior phase.
_EXPERIMENT_DOMAIN = "experiment/1"
_SWEEP_AXIS_DOMAIN = "sweep-axis/1"
_EXPERIMENT_ENGINE_DOMAIN = "experiment-engine/1"
_COMPARISON_DOMAIN = "backtest-comparison/1"


def _canonical_json(payload: object) -> str:
    """Serialize ``payload`` with the project's canonical-JSON discipline (§11)."""
    return json.dumps(
        payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )


def _sha256(payload: str) -> str:
    return f"sha256:{sha256_hex(payload.encode('utf-8'))}"


def sweep_axis_id(parameter: str, sorted_canonical_values: list[str]) -> str:
    """``sha256(domain, parameter, canonical JSON of the sorted values)`` (locked §4).

    An axis is a *set* of values for one parameter, so identity sorts the canonicalized
    values: ``(1, 5)`` and ``(5, 1)`` yield the same id. The caller passes the values
    already reduced to their canonical string form and sorted, so this function is a
    pure hash and never re-orders numerically.
    """
    payload = _SEP.join(
        (_SWEEP_AXIS_DOMAIN, parameter, _canonical_json(sorted_canonical_values))
    )
    return _sha256(payload)


def experiment_id(
    *,
    name: str,
    spec_version: str,
    base_request: dict[str, object],
    sorted_axis_ids: list[str],
    risk_free_per_period: str,
    periods_per_year: str,
) -> str:
    """The identity of a whole experiment — declaration **and** run convention (§4).

    Folds the experiment name, the specification-schema version, the exact base
    :class:`~quantforge.backtest.spec.BacktestSpecification` request (its canonical
    ``to_dict``, which itself pins both corpus snapshots — locked D2), every axis id
    (sorted, so axis declaration order never changes the id), and the annualization run
    convention threaded to every child (locked D5). Same declaration + same convention ⇒
    same id on any machine.
    """
    payload = _SEP.join(
        (
            _EXPERIMENT_DOMAIN,
            name,
            spec_version,
            _canonical_json(base_request),
            _canonical_json(sorted_axis_ids),
            risk_free_per_period,
            periods_per_year,
        )
    )
    return _sha256(payload)


def experiment_result_hash(run_digests: list[dict[str, object]]) -> str:
    """``sha256`` over the ordered ``(coordinate, backtest_id)`` digests (locked §4).

    ``run_digests`` is the ordered list of per-coordinate digests (each the sorted
    coordinate pairs plus the sealed child ``backtest_id``) in canonical-coordinate
    order; serialized with the canonical-JSON discipline so equal families always yield
    identical bytes. Sensitive to every child id: a single differing child changes it.
    """
    return _sha256(_canonical_json(run_digests))


def experiment_result_id(
    *, experiment_id: str, experiment_engine_version_id: str, result_hash: str
) -> str:
    """``sha256(experiment_id, engine version, result_hash)`` — the sidecar key (§4).

    The :class:`~quantforge.experiment.result.ExperimentResult`'s ``research_result_id``
    aliases this, so the record persists to the shared write-once sidecar with no new
    store (locked D4). It pins both the request (``experiment_id``), the engine logic,
    and the sealed output (``result_hash``).
    """
    payload = _SEP.join((experiment_id, experiment_engine_version_id, result_hash))
    return _sha256(payload)


def comparison_id(
    *,
    comparison_version_id: str,
    statistic_key: str,
    order: str,
    sorted_member_backtest_ids: list[str],
) -> str:
    """``sha256(domain, version, statistic, order, sorted member ids)`` (locked §4).

    A comparison's identity is the *set* of members plus the ranking rule (statistic +
    order), so re-running the same comparison over the same members reproduces the id
    regardless of the order the member ids were supplied in.
    """
    payload = _SEP.join(
        (
            _COMPARISON_DOMAIN,
            comparison_version_id,
            statistic_key,
            order,
            _canonical_json(sorted_member_backtest_ids),
        )
    )
    return _sha256(payload)


def experiment_engine_version_id() -> str:
    """``sha256(domain "experiment-engine/1")`` — the engine-logic version (§4).

    The comparative-research layer performs no numeric derivation of its own (it
    orchestrates Phase 12 and ranks existing statistics), so its version folds only the
    domain tag; a change to the orchestration logic bumps the tag, yielding a distinct
    id without altering any already-computed one.
    """
    return _sha256(_EXPERIMENT_ENGINE_DOMAIN)


def comparison_version_id() -> str:
    """``sha256(domain "backtest-comparison/1")`` — comparison-logic version (§4)."""
    return _sha256(_COMPARISON_DOMAIN)
