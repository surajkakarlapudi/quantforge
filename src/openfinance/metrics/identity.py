"""The deterministic ``metric_id`` — the identity of one metric *request* (§6.2).

``metric_id`` pins the request that produced a metric — the formula version, the
engine version, the filer, the fiscal period, and the knowledge-state boundary — so
that re-running the same request reproduces the same id **and** the same value
(determinism made checkable, §16). It deliberately does **not** hash the resulting
*value*: the id names the question, the value + provenance are the derived answer.

Follows the §11 identity discipline verbatim: ``sha256:``-prefixed, NUL-joined
components, no wall-clock / RNG / ordering dependence.
"""

from __future__ import annotations

from openfinance.sec.artifacts import sha256_hex

__all__ = ["metric_id"]

_SEP = "\x00"


def metric_id(
    *,
    formula_id: str,
    metric_engine_version_id: str,
    company_id: str,
    period_key: str,
    boundary_key: str,
) -> str:
    """Return ``sha256(formula_id, engine_version, company_id, period, boundary)``.

    ``boundary_key`` is ``"pit:" + as_of_utc`` (PIT) or ``"rev:" +
    dataset_version_id`` (REVISED), so a PIT and a REVISED metric of the same
    formula/period never collide (§6.2).
    """
    payload = _SEP.join(
        (
            formula_id,
            metric_engine_version_id,
            company_id,
            period_key,
            boundary_key,
        )
    )
    return f"sha256:{sha256_hex(payload.encode('utf-8'))}"
