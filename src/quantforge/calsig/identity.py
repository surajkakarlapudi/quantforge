"""The content-addressed identities for the calibration-significance layer (§10, §11).

Every identity here follows the project's §11 discipline verbatim - ``sha256:``
prefixed, ``_SEP = "\\x00"`` NUL-joined components, canonical JSON
(``sort_keys=True, ensure_ascii=False, separators=(",",":")``) for any structured
payload, and **no** dependence on the wall clock, a random value, an object ``id()``, or
iteration order. Re-declaring the identical request over the identical sealed
calibration reproduces every id on any machine - the identical construction
:mod:`quantforge.mintrl.identity` uses, with a fresh domain tag so a Phase 29 id can
never collide with a lower-layer one.

The engine-version id (``calibration_significance_engine_version_id``) is **not**
computed here: it is a property of
:class:`~quantforge.calsig.version.CalibrationSignificanceEngineVersion` (it folds the
pinned decimal context, the statistical-method version, and the normal-primitive
version), so there is a single source of truth for it, never a second competing
implementation.

Like Phase 28, Phase 29 references a *sealed artifact* - exactly one
:class:`~quantforge.calibration.result.RiskForecastCalibration` - by its
``result_hash``. A calibration record's ``result_hash`` already content-addresses its
full per-window answer (and its ``risk_forecast_calibration_id`` in turn folds that
``result_hash`` and, transitively, the walk-forward / optimization / risk-model / factor
chain beneath it); so folding the source calibration's ``result_hash`` here makes the
significance test's id **transitively** sensitive to any change in the source
calibration or anything beneath it (CS-1).

The ids, and what each pins (§10):

    calibration_significance_result_hash = sha256( canonical JSON over the ordered
        computed-output cells: the single aggregate significance summary block ) -
        sensitive to every computed statistic (mean, standard error, t, p, direction,
        status).
    calibration_significance_id = sha256( domain "calsig/1",
        calibration_significance_engine_version_id, name, spec_version,
        source_calibration_id, source_result_hash, null_mean_ratio,
        calibration_significance_result_hash )
        - so the id is sensitive to any change in the request, the referenced
          calibration, the null mean tested, or the computed answer. Honestly
          self-verifying.

``research_result_id`` aliases ``calibration_significance_id`` (a single id - the
significance is a value record whose id already folds its output).
"""

from __future__ import annotations

import json

from quantforge.sec.artifacts import sha256_hex

__all__ = [
    "calibration_significance_id",
    "calibration_significance_result_hash",
]

# The NUL separator shared across every id space in the project (data-model §11); it
# cannot occur in a hash, a name, a decimal string, or a canonical-JSON payload, so a
# joined payload is unambiguous.
_SEP = "\x00"

# Domain tag. A new tag (or a bump) yields distinct ids without altering any
# already-computed id - the extensibility discipline shared with every prior phase. The
# ``calsig-engine/1`` tag lives on the version dataclass; here only the record tag.
_CALSIG_DOMAIN = "calsig/1"


def _canonical_json(payload: object) -> str:
    """Serialize ``payload`` with the project's canonical-JSON discipline (§11)."""
    return json.dumps(
        payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )


def _sha256(payload: str) -> str:
    return f"sha256:{sha256_hex(payload.encode('utf-8'))}"


def calibration_significance_result_hash(
    output_cells: list[dict[str, object]],
) -> str:
    """``sha256`` over the ordered computed-output cells - the answer seal (§10).

    ``output_cells`` is the ordered list of computed cells (for Phase 29, the single
    aggregate significance summary), each tagged by its block and reduced to a canonical
    dict, serialized with the canonical-JSON discipline so equal answers always yield
    identical bytes. Sensitive to every computed statistic: a single differing cell
    changes it.
    """
    return _sha256(_canonical_json(output_cells))


def calibration_significance_id(
    *,
    calibration_significance_engine_version_id: str,
    name: str,
    spec_version: str,
    source_calibration_id: str,
    source_result_hash: str,
    null_mean_ratio: str,
    result_hash: str,
) -> str:
    """The identity of a significance record - request, input **and** answer (§10).

    Folds the engine-logic + method + normal + decimal-context version
    (``calibration_significance_engine_version_id``), the declared request (name, spec
    version), the **referenced content**: the source calibration's
    ``research_result_id`` and its ``result_hash`` (so the id is transitively sensitive
    to any change in the sealed calibration or anything beneath it), the
    ``NULL_MEAN_RATIO`` tested, and the
    sealed ``calibration_significance_result_hash`` over the computed answer. Same
    request + same sealed calibration => same id on any machine; a change to *any* fold
    yields a different id, never a silently different record under the same id (CS-1).
    """
    payload = _SEP.join(
        (
            _CALSIG_DOMAIN,
            calibration_significance_engine_version_id,
            name,
            spec_version,
            source_calibration_id,
            source_result_hash,
            null_mean_ratio,
            result_hash,
        )
    )
    return _sha256(payload)
