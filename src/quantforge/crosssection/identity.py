"""The content-addressed identities for the cross-sectional-regression layer (§5).

Every identity here follows the project's §11 discipline verbatim - ``sha256:``
prefixed, ``_SEP = "\\x00"`` NUL-joined components, canonical JSON (``sort_keys=True,
ensure_ascii=False, separators=(",",":")``) for any structured payload, and **no**
dependence on the wall clock, a random value, an object ``id()``, or iteration order.
Re-declaring the identical request over the identical pinned corpora reproduces every
id, on any machine - the identical construction Phase 16's
:mod:`quantforge.diagnostics.identity` and Phase 17's
:mod:`quantforge.attribution.identity` use, with a fresh domain tag so a Phase 18 id can
never collide with a lower-layer one.

The engine-version id (``crosssection_engine_version_id``) is **not** computed here: it
is a property of
:class:`~quantforge.crosssection.version.CrossSectionEngineVersion` (it folds the pinned
decimal context and the formula-method version), so there is a single source of truth
for it, never a second competing implementation.

Like Phase 16 (and unlike Phase 17, which references sealed backtests by their
``result_hash``), Phase 18 reads the **raw corpora** and references them by **corpus
pin** - the content-addressed fundamentals ``dataset_version_id`` and market
``market_dataset_version_id`` - so the id stays sensitive to any corpus change without
folding a sealed artifact hash.

The ids, and what each pins (§5):

    crosssection_result_hash = sha256( canonical JSON over the ordered computed outputs:
                                    the per-date coefficient panel (schedule order),
                                    then the aggregated premia block (factor order),
                                    each reduced to its canonical cell form )
                            - sensitive to every computed statistic.
    crosssection_id = sha256( domain "crosssection/1",
                                    crosssection_engine_version_id, name, spec_version,
                                    the ORDERED factor descriptors, universe
                                    specification_id, schedule_id, horizon_days,
                                    include_intercept, both corpus pins, and
                                    crosssection_result_hash )
                            - so the id is sensitive to any change in the request,
                              either corpus, or the computed answer. Honestly
                              self-verifying.

The factor descriptor list is folded in **request order** (not sorted): order is
semantic - it fixes the design-matrix column order and therefore the coefficient labels
- so ``[(a, p), (b, p)]`` and ``[(b, p), (a, p)]`` are distinct requests with distinct
ids.

``research_result_id`` aliases ``crosssection_id`` (a single id - the regression, like a
diagnostic, is a value record whose id already folds its output).
"""

from __future__ import annotations

import json

from quantforge.sec.artifacts import sha256_hex

__all__ = [
    "crosssection_id",
    "crosssection_result_hash",
]

# The NUL separator shared across every id space in the project (data-model §11); it
# cannot occur in a hash, a name, a decimal string, or a canonical-JSON payload, so a
# joined payload is unambiguous.
_SEP = "\x00"

# Domain tag. A new tag (or a bump) yields distinct ids without altering any
# already-computed id - the extensibility discipline shared with every prior phase. The
# ``crosssection-engine/1`` tag lives on the version dataclass; here only the record
# tag.
_CROSSSECTION_DOMAIN = "crosssection/1"


def _canonical_json(payload: object) -> str:
    """Serialize ``payload`` with the project's canonical-JSON discipline (§11)."""
    return json.dumps(
        payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )


def _sha256(payload: str) -> str:
    return f"sha256:{sha256_hex(payload.encode('utf-8'))}"


def crosssection_result_hash(output_cells: list[dict[str, object]]) -> str:
    """``sha256`` over the ordered computed-output cells - the answer seal (§5).

    ``output_cells`` is the ordered list of computed-statistic cells (each a canonical
    dict, in the record's stored order: the per-date coefficient block in schedule
    order, then the premia block in factor order), serialized with the canonical-JSON
    discipline so equal answers always yield identical bytes. Sensitive to every
    computed statistic: a single differing cell changes it.
    """
    return _sha256(_canonical_json(output_cells))


def crosssection_id(
    *,
    crosssection_engine_version_id: str,
    name: str,
    spec_version: str,
    factor_descriptors: list[list[str]],
    universe_specification_id: str,
    schedule_id: str,
    horizon_days: int,
    include_intercept: bool,
    dataset_version_id: str,
    market_dataset_version_id: str,
    result_hash: str,
) -> str:
    """The identity of a whole regression record - request, corpora **and** answer (§5).

    Folds the engine-logic + formula + decimal-context version
    (``crosssection_engine_version_id``), the full declared request (name, spec version,
    the **ordered** factor descriptors ``[(metric_key, period_key), ...]``, the universe
    ``specification_id``, the evaluation ``schedule_id``, the forward-horizon
    trading-day count, and the intercept flag), **both** content-addressed corpus pins
    (fundamentals + market), and the sealed ``crosssection_result_hash`` over the
    computed answer. Same request + same pinned corpora ⇒ same id on any machine; a
    change to *any* fold yields a different id, never a silently different record under
    the same id (XS-1).

    The factor descriptors are folded as an **ordered** JSON array - order is semantic
    (it fixes the regression's column order and coefficient labels), so it is preserved,
    never sorted. No annualization convention enters the id: the Fama-MacBeth
    t-statistic is per-period.
    """
    payload = _SEP.join(
        (
            _CROSSSECTION_DOMAIN,
            crosssection_engine_version_id,
            name,
            spec_version,
            _canonical_json(factor_descriptors),
            universe_specification_id,
            schedule_id,
            str(horizon_days),
            str(include_intercept),
            dataset_version_id,
            market_dataset_version_id,
            result_hash,
        )
    )
    return _sha256(payload)
