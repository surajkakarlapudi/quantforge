"""The content-addressed identities for the risk-forecast-calibration layer (§10, §11).

Every identity here follows the project's §11 discipline verbatim - ``sha256:``
prefixed, ``_SEP = "\\x00"`` NUL-joined components, canonical JSON
(``sort_keys=True, ensure_ascii=False, separators=(",",":")``) for any structured
payload, and **no** dependence on the wall clock, a random value, an object ``id()``, or
iteration order. Re-declaring the identical request over the identical sealed
walk-forward reproduces every id on any machine - the identical construction
:mod:`quantforge.multiplicity.identity` uses, with a fresh domain tag so a Phase 26 id
can never collide with a lower-layer one.

The engine-version id (``risk_forecast_calibration_engine_version_id``) is **not**
computed here: it is a property of
:class:`~quantforge.calibration.version.RiskForecastCalibrationEngineVersion` (it folds
the pinned decimal context and the statistical-method version), so there is a single
source of truth for it, never a second competing implementation.

Like Phase 25, Phase 26 references a *sealed artifact* - exactly one
:class:`~quantforge.walkforward.result.WalkForwardEvaluation` - by its
``result_hash``. A walk-forward record's ``result_hash`` already content-addresses
its full per-window answer (and its ``walk_forward_id`` in turn folds that
``result_hash`` and, transitively, the optimization / risk-model / factor chain
beneath it); so folding the source walk's ``result_hash`` here makes the
calibration's id **transitively** sensitive to any change in the source walk-forward
or anything beneath it (RC-1).

The ids, and what each pins (§10):

    risk_forecast_calibration_result_hash = sha256( canonical JSON over the ordered
        computed-output cells: the coverage descriptor (window / calibratable /
        excluded counts), then each calibratable window's ``(index,
        predicted_variance, realized_variance, variance_ratio, volatility_ratio)``
        in source order, then each excluded window's ``(index, reason)``, then the
        aggregate calibration summary ) - sensitive to every computed ratio and
        aggregate.
    risk_forecast_calibration_id = sha256( domain "calibration/1",
        risk_forecast_calibration_engine_version_id, name, spec_version,
        source_walk_forward_id, source_result_hash, min_calibratable_windows,
        risk_forecast_calibration_result_hash )
        - so the id is sensitive to any change in the request, the referenced walk, the
          calibratable-windows floor, or the computed answer. Honestly self-verifying.

``research_result_id`` aliases ``risk_forecast_calibration_id`` (a single id - the
calibration is a value record whose id already folds its output).
"""

from __future__ import annotations

import json

from quantforge.sec.artifacts import sha256_hex

__all__ = [
    "risk_forecast_calibration_id",
    "risk_forecast_calibration_result_hash",
]

# The NUL separator shared across every id space in the project (data-model §11); it
# cannot occur in a hash, a name, a decimal string, or a canonical-JSON payload, so a
# joined payload is unambiguous.
_SEP = "\x00"

# Domain tag. A new tag (or a bump) yields distinct ids without altering any
# already-computed id - the extensibility discipline shared with every prior phase. The
# ``calibration-engine/1`` tag lives on the version dataclass; here only the record tag.
_CALIBRATION_DOMAIN = "calibration/1"


def _canonical_json(payload: object) -> str:
    """Serialize ``payload`` with the project's canonical-JSON discipline (§11)."""
    return json.dumps(
        payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )


def _sha256(payload: str) -> str:
    return f"sha256:{sha256_hex(payload.encode('utf-8'))}"


def risk_forecast_calibration_result_hash(
    output_cells: list[dict[str, object]],
) -> str:
    """``sha256`` over the ordered computed-output cells - the answer seal (§10).

    ``output_cells`` is the ordered list of computed cells (the coverage descriptor,
    then the calibratable-window cells, then the excluded-window cells, then the
    aggregate summary), each tagged by its block and reduced to a canonical dict,
    serialized with the canonical-JSON discipline so equal answers always yield
    identical bytes. Sensitive to every computed ratio and aggregate: a single
    differing cell changes it.
    """
    return _sha256(_canonical_json(output_cells))


def risk_forecast_calibration_id(
    *,
    calibration_engine_version_id: str,
    name: str,
    spec_version: str,
    source_walk_forward_id: str,
    source_result_hash: str,
    min_calibratable_windows: int,
    result_hash: str,
) -> str:
    """The identity of a whole calibration record - request, input **and** answer (§10).

    Folds the engine-logic + method + decimal-context version
    (``calibration_engine_version_id``), the declared request (name, spec version),
    the **referenced content**: the source walk-forward's ``research_result_id`` and
    its ``result_hash`` (so the id is transitively sensitive to any change in the
    sealed walk or anything beneath it), the ``MIN_CALIBRATABLE_WINDOWS`` floor that
    governs ``calibration_status``, and the sealed
    ``risk_forecast_calibration_result_hash`` over the computed answer. Same request
    + same sealed walk => same id on any machine; a change to *any* fold yields a
    different id, never a silently different record under the same id (RC-1).
    """
    payload = _SEP.join(
        (
            _CALIBRATION_DOMAIN,
            calibration_engine_version_id,
            name,
            spec_version,
            source_walk_forward_id,
            source_result_hash,
            str(min_calibratable_windows),
            result_hash,
        )
    )
    return _sha256(payload)
