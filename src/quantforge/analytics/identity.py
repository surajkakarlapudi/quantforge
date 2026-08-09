"""The content-addressed identities for the performance-analytics layer (§L).

Every identity here follows the project's §11 discipline verbatim — ``sha256:``
prefixed, ``_SEP = "\\x00"`` NUL-joined components, canonical JSON (``sort_keys=True,
ensure_ascii=False, separators=(",",":")``) for any structured payload, and **no**
dependence on the wall clock, a random value, an object ``id()``, or iteration order.
Re-declaring the identical request over the identical sealed inputs reproduces every id,
on any machine — the identical construction Phase 12's
:mod:`quantforge.backtest.identity` uses, with a fresh domain tag so a Phase 15 id can
never collide with a lower-layer one.

The engine-version id (``analytics_engine_version_id``) is **not** computed here: it is
a property of :class:`~quantforge.analytics.version.AnalyticsEngineVersion` (it folds
the pinned decimal context and the formula-method version, exactly as
:class:`~quantforge.backtest.version.BacktestEngineVersion` does), so there is a single
source of truth for it, never a second competing implementation.

The ids, and what each pins (§L):

    analytics_result_hash = sha256( canonical JSON over the ordered computed outputs:
                                    absolute + relative + var, each reduced to its (key,
                                    status, value) cells )
                            — sensitive to the computed answer, like
                              ``BacktestResult.result_hash``.
    analytics_id = sha256( domain "analytics/1", analytics_engine_version_id,
                                    the spec identity (name, spec_version, subject_id,
                                    benchmark_id or "", sorted var_confidences,
                                    risk_free_per_period, periods_per_year), the
                                    referenced content hashes (subject result_hash,
                                    benchmark result_hash or ""), analytics_result_hash
                                    )
                            — so the id is sensitive to *any* change in either
                            referenced
                              backtest, the convention, the requested parameters, or the
                              computed answer. Honestly self-verifying.

``research_result_id`` aliases ``analytics_id`` (a single id, mirroring
``BacktestResult.backtest_id`` — analytics, like a backtest, is a value record whose id
already folds its output).
"""

from __future__ import annotations

import json

from quantforge.sec.artifacts import sha256_hex

__all__ = [
    "analytics_id",
    "analytics_result_hash",
]

# The NUL separator shared across every id space in the project (data-model §11); it
# cannot occur in a hash, a name, a decimal string, or a canonical-JSON payload, so a
# joined payload is unambiguous.
_SEP = "\x00"

# Domain tag. A new tag (or a bump) yields distinct ids without altering any
# already-computed id — the extensibility discipline shared with every prior phase. The
# ``analytics-engine/1`` tag lives on the version dataclass; here only the record tag.
_ANALYTICS_DOMAIN = "analytics/1"


def _canonical_json(payload: object) -> str:
    """Serialize ``payload`` with the project's canonical-JSON discipline (§11)."""
    return json.dumps(
        payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )


def _sha256(payload: str) -> str:
    return f"sha256:{sha256_hex(payload.encode('utf-8'))}"


def analytics_result_hash(output_cells: list[dict[str, object]]) -> str:
    """``sha256`` over the ordered computed-output cells — the answer seal (§L).

    ``output_cells`` is the ordered list of computed-statistic cells (each a canonical
    ``(key, status, value)`` dict, in the record's stored order: absolute, then
    relative, then var), serialized with the canonical-JSON discipline so equal answers
    always yield identical bytes. Sensitive to every computed statistic: a single
    differing cell changes it.
    """
    return _sha256(_canonical_json(output_cells))


def analytics_id(
    *,
    analytics_engine_version_id: str,
    name: str,
    spec_version: str,
    subject_id: str,
    benchmark_id: str | None,
    sorted_var_confidences: list[str],
    risk_free_per_period: str,
    periods_per_year: str,
    subject_result_hash: str,
    benchmark_result_hash: str | None,
    result_hash: str,
) -> str:
    """The identity of a whole analytics record — request, inputs **and** answer (§L).

    Folds the engine-logic + formula + decimal-context version
    (``analytics_engine_version_id``), the full declared request (name, spec version,
    subject / benchmark ids, the requested VaR confidences sorted so their order never
    changes the id, and the annualization convention), the **referenced content hashes**
    (the ``result_hash`` of the subject and — when present — the benchmark, so the id is
    sensitive to any change in either sealed input), and the sealed
    ``analytics_result_hash`` over the computed answer. Same request + same sealed
    inputs ⇒ same id on any machine; a change to *any* fold yields a different id, never
    a silently different record under the same id.

    ``benchmark_id`` / ``benchmark_result_hash`` fold as the empty string when absent,
    so an absolute-only record has a stable, benchmark-free identity.
    """
    payload = _SEP.join(
        (
            _ANALYTICS_DOMAIN,
            analytics_engine_version_id,
            name,
            spec_version,
            subject_id,
            benchmark_id or "",
            _canonical_json(sorted_var_confidences),
            risk_free_per_period,
            periods_per_year,
            subject_result_hash,
            benchmark_result_hash or "",
            result_hash,
        )
    )
    return _sha256(payload)
