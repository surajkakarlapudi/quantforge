"""The content-addressed identities for the signal-diagnostics layer (§5).

Every identity here follows the project's §11 discipline verbatim — ``sha256:``
prefixed, ``_SEP = "\\x00"`` NUL-joined components, canonical JSON (``sort_keys=True,
ensure_ascii=False, separators=(",",":")``) for any structured payload, and **no**
dependence on the wall clock, a random value, an object ``id()``, or iteration order.
Re-declaring the identical request over the identical pinned corpora reproduces every
id, on any machine — the identical construction Phase 15's
:mod:`quantforge.analytics.identity` uses, with a fresh domain tag so a Phase 16 id can
never collide with a lower-layer one.

The engine-version id (``signal_diagnostics_engine_version_id``) is **not** computed
here: it is a property of
:class:`~quantforge.diagnostics.version.SignalDiagnosticsEngineVersion` (it folds the
pinned decimal context and the formula-method version), so there is a single source of
truth for it, never a second competing implementation.

Unlike Phase 15 (which references sealed backtests by their ``result_hash``), Phase 16
reads the **raw corpora** and references them by **corpus pin** — the content-addressed
fundamentals ``dataset_version_id`` and market ``market_dataset_version_id`` — so the id
stays sensitive to any corpus change without folding a sealed artifact hash (D9).

The ids, and what each pins (§5):

    diagnostics_result_hash = sha256( canonical JSON over the ordered computed outputs:
                                    the per-date IC cells + bucket means + spread, then
                                    the quantile profile, then the IC summary, each
                                    reduced to its canonical cell form )
                            — sensitive to every computed statistic.
    diagnostics_id = sha256( domain "diagnostics/1",
                                    signal_diagnostics_engine_version_id, the spec
                                    identity (name, spec_version, signal, period_key,
                                    universe specification_id, schedule_id,
                                    horizon_days,
                                    quantiles, sorted ic_methods), both corpus pins
                                    (dataset_version_id, market_dataset_version_id),
                                    diagnostics_result_hash )
                            — so the id is sensitive to any change in the request,
                              either corpus, or the computed answer. Honestly
                              self-verifying.

``research_result_id`` aliases ``diagnostics_id`` (a single id — the diagnostic, like a
backtest, is a value record whose id already folds its output).
"""

from __future__ import annotations

import json

from quantforge.sec.artifacts import sha256_hex

__all__ = [
    "diagnostics_id",
    "diagnostics_result_hash",
]

# The NUL separator shared across every id space in the project (data-model §11); it
# cannot occur in a hash, a name, a decimal string, or a canonical-JSON payload, so a
# joined payload is unambiguous.
_SEP = "\x00"

# Domain tag. A new tag (or a bump) yields distinct ids without altering any
# already-computed id — the extensibility discipline shared with every prior phase. The
# ``diagnostics-engine/1`` tag lives on the version dataclass; here only the record tag.
_DIAGNOSTICS_DOMAIN = "diagnostics/1"


def _canonical_json(payload: object) -> str:
    """Serialize ``payload`` with the project's canonical-JSON discipline (§11)."""
    return json.dumps(
        payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )


def _sha256(payload: str) -> str:
    return f"sha256:{sha256_hex(payload.encode('utf-8'))}"


def diagnostics_result_hash(output_cells: list[dict[str, object]]) -> str:
    """``sha256`` over the ordered computed-output cells — the answer seal (§5).

    ``output_cells`` is the ordered list of computed-statistic cells (each a canonical
    dict, in the record's stored order: the per-date IC block, then the quantile-profile
    block, then the IC-summary block), serialized with the canonical-JSON discipline so
    equal answers always yield identical bytes. Sensitive to every computed statistic: a
    single differing cell changes it.
    """
    return _sha256(_canonical_json(output_cells))


def diagnostics_id(
    *,
    signal_diagnostics_engine_version_id: str,
    name: str,
    spec_version: str,
    signal: str,
    period_key: str,
    universe_specification_id: str,
    schedule_id: str,
    horizon_days: int,
    quantiles: int,
    sorted_ic_methods: list[str],
    dataset_version_id: str,
    market_dataset_version_id: str,
    result_hash: str,
) -> str:
    """The identity of a whole diagnostics record — request, corpora **and** answer
    (§5).

    Folds the engine-logic + formula + decimal-context version
    (``signal_diagnostics_engine_version_id``), the full declared request (name, spec
    version, signal metric key, canonical period key, universe ``specification_id``, the
    evaluation ``schedule_id``, the forward-horizon trading-day count, the quantile
    count, and the requested IC methods sorted so their order never changes the id),
    **both** content-addressed corpus pins (fundamentals + market), and the sealed
    ``diagnostics_result_hash`` over the computed answer. Same request + same pinned
    corpora ⇒ same id on any machine; a change to *any* fold yields a different id,
    never a silently different record under the same id (SD-1).
    """
    payload = _SEP.join(
        (
            _DIAGNOSTICS_DOMAIN,
            signal_diagnostics_engine_version_id,
            name,
            spec_version,
            signal,
            period_key,
            universe_specification_id,
            schedule_id,
            str(horizon_days),
            str(quantiles),
            _canonical_json(sorted_ic_methods),
            dataset_version_id,
            market_dataset_version_id,
            result_hash,
        )
    )
    return _sha256(payload)
