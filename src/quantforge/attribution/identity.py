"""The content-addressed identities for the factor-attribution layer (§8).

Every identity here follows the project's §11 discipline verbatim — ``sha256:``
prefixed, ``_SEP = "\\x00"`` NUL-joined components, canonical JSON (``sort_keys=True,
ensure_ascii=False, separators=(",",":")``) for any structured payload, and **no**
dependence on the wall clock, a random value, an object ``id()``, or iteration order.
Re-declaring the identical request over the identical sealed inputs reproduces every id,
on any machine — the identical construction Phase 15's
:mod:`quantforge.analytics.identity` uses, with a fresh domain tag so a Phase 17 id can
never collide with a lower-layer one.

The engine-version id (``attribution_engine_version_id``) is **not** computed here: it
is a property of :class:`~quantforge.attribution.version.AttributionEngineVersion` (it
folds the pinned decimal context and the formula-method version, exactly as
:class:`~quantforge.analytics.version.AnalyticsEngineVersion` does), so there is a
single source of truth for it, never a second competing implementation.

The ids, and what each pins (§8):

    attribution_result_hash = sha256( canonical JSON over the ordered computed-output
                                    cells: coefficients + diagnostics + decomposition +
                                    residual digest, each reduced to its canonical form
                                    )
                            — sensitive to the computed answer, like
                              ``analytics_result_hash`` /
                              ``BacktestResult.result_hash``.
    attribution_id = sha256( domain "attribution/1", attribution_engine_version_id,
                                    the spec identity (name, spec_version, subject_id,
                                    the ORDERED factor id list, risk_free_per_period,
                                    periods_per_year), the referenced content hashes
                                    (the
                                    subject result_hash and the ORDERED factor
                                    result_hashes), attribution_result_hash )
                            — so the id is sensitive to *any* change in the subject or
                            any
                              factor backtest, the factor order, the convention, the
                              requested factors, or the computed answer. Honestly
                              self-verifying.

``research_result_id`` aliases ``attribution_id`` (a single id, mirroring
``analytics_id`` / ``BacktestResult.backtest_id`` — an attribution, like an analytics
record, is a value record whose id already folds its output). The factor list is folded
in **request order** (not sorted): order is semantic — it fixes the design-matrix column
order and therefore the coefficient labels — so ``(value, size)`` and ``(size, value)``
are distinct requests with distinct ids.
"""

from __future__ import annotations

import json

from quantforge.sec.artifacts import sha256_hex

__all__ = [
    "attribution_id",
    "attribution_result_hash",
    "residual_digest",
]

# The NUL separator shared across every id space in the project (data-model §11); it
# cannot occur in a hash, a name, a decimal string, or a canonical-JSON payload, so a
# joined payload is unambiguous.
_SEP = "\x00"

# Domain tag. A new tag (or a bump) yields distinct ids without altering any
# already-computed id — the extensibility discipline shared with every prior phase. The
# ``attribution-engine/1`` tag lives on the version dataclass; here only the record tag.
_ATTRIBUTION_DOMAIN = "attribution/1"


def _canonical_json(payload: object) -> str:
    """Serialize ``payload`` with the project's canonical-JSON discipline (§11)."""
    return json.dumps(
        payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )


def _sha256(payload: str) -> str:
    return f"sha256:{sha256_hex(payload.encode('utf-8'))}"


def attribution_result_hash(output_cells: list[dict[str, object]]) -> str:
    """``sha256`` over the ordered computed-output cells — the answer seal (§8).

    ``output_cells`` is the ordered list of computed cells (coefficients, then
    diagnostics, then decomposition, then the residual-digest cell), each tagged by its
    block and reduced to a canonical dict, serialized with the canonical-JSON discipline
    so equal answers always yield identical bytes. Sensitive to every computed value: a
    single differing cell changes it.
    """
    return _sha256(_canonical_json(output_cells))


def residual_digest(residuals: list[str]) -> str:
    """A deterministic ``sha256:`` digest of the ordered residual series (D4).

    Per approved decision D4 the record persists **only** this digest, not the residual
    vector itself — keeping the sealed record compact while still content-addressing the
    exact residuals the regression produced (a changed residual series yields a
    different digest, hence a different ``result_hash`` and ``attribution_id``).
    ``residuals`` is the ordered list of canonical residual decimal strings; it is
    serialized with the canonical-JSON discipline so the digest is byte-stable across
    machines. The digest is folded into the sealed output cells (a ``residual`` block),
    never divided from the series it summarizes.
    """
    return _sha256(_canonical_json(residuals))


def attribution_id(
    *,
    attribution_engine_version_id: str,
    name: str,
    spec_version: str,
    subject_id: str,
    factor_ids: list[str],
    risk_free_per_period: str,
    periods_per_year: str,
    subject_result_hash: str,
    factor_result_hashes: list[str],
    result_hash: str,
) -> str:
    """The identity of a whole attribution record — request, inputs **and** answer (§8).

    Folds the engine-logic + formula + decimal-context version
    (``attribution_engine_version_id``), the full declared request (name, spec version,
    subject id, the **ordered** factor ids, and the annualization convention), the
    **referenced content hashes** (the ``result_hash`` of the subject and of each factor
    in the same order, so the id is sensitive to any change in any sealed input), and
    the sealed ``attribution_result_hash`` over the computed answer. Same request + same
    sealed inputs ⇒ same id on any machine; a change to *any* fold yields a different
    id, never a silently different record under the same id.

    Both factor lists are folded as ordered JSON arrays — order is semantic (it fixes
    the regression's column order and coefficient labels), so it is preserved, never
    sorted.
    """
    payload = _SEP.join(
        (
            _ATTRIBUTION_DOMAIN,
            attribution_engine_version_id,
            name,
            spec_version,
            subject_id,
            _canonical_json(factor_ids),
            risk_free_per_period,
            periods_per_year,
            subject_result_hash,
            _canonical_json(factor_result_hashes),
            result_hash,
        )
    )
    return _sha256(payload)
