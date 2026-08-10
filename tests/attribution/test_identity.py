"""Content-addressed identity: determinism and sensitivity to every fold (§8, §11).

These tests pin the §8 identity discipline for the attribution layer: ``attribution_id``
is a ``sha256:``-prefixed pure content hash that reproduces byte-for-byte on
re-derivation and changes if — and only if — one of its declared folds changes (the
engine version, any request field, the factor order, any referenced content hash, or the
computed answer).
:func:`residual_digest` and :func:`attribution_result_hash` are likewise deterministic
canonical-JSON digests.
"""

from __future__ import annotations

from quantforge.attribution.identity import (
    attribution_id,
    attribution_result_hash,
    residual_digest,
)

_BASE: dict[str, object] = {
    "attribution_engine_version_id": "sha256:engine",
    "name": "phase17",
    "spec_version": "attribution/1",
    "subject_id": "sha256:subject",
    "factor_ids": ["sha256:f1", "sha256:f2"],
    "risk_free_per_period": "0",
    "periods_per_year": "1",
    "subject_result_hash": "sha256:rh-subject",
    "factor_result_hashes": ["sha256:rh-f1", "sha256:rh-f2"],
    "result_hash": "sha256:answer",
}


def _id(**overrides: object) -> str:
    payload = dict(_BASE)
    payload.update(overrides)
    return attribution_id(**payload)  # type: ignore[arg-type]


class TestDeterminism:
    def test_prefixed_and_reproducible(self) -> None:
        first = _id()
        second = _id()
        assert first == second
        assert first.startswith("sha256:")


class TestSensitivity:
    def test_engine_version_changes_id(self) -> None:
        assert _id(attribution_engine_version_id="sha256:other") != _id()

    def test_name_changes_id(self) -> None:
        assert _id(name="other") != _id()

    def test_subject_id_changes_id(self) -> None:
        assert _id(subject_id="sha256:other") != _id()

    def test_convention_changes_id(self) -> None:
        assert _id(risk_free_per_period="0.01") != _id()
        assert _id(periods_per_year="12") != _id()

    def test_factor_order_changes_id(self) -> None:
        # Order is semantic — reversing the factor list is a distinct request.
        reversed_factors = list(reversed(["sha256:f1", "sha256:f2"]))
        assert _id(factor_ids=reversed_factors) != _id()

    def test_referenced_content_hash_changes_id(self) -> None:
        # Sensitive to any change in a sealed input, even with an unchanged request.
        assert _id(subject_result_hash="sha256:drift") != _id()
        assert _id(factor_result_hashes=["sha256:rh-f1", "sha256:drift"]) != _id()

    def test_answer_changes_id(self) -> None:
        assert _id(result_hash="sha256:different") != _id()


class TestResultHashAndResidualDigest:
    def test_result_hash_deterministic_and_answer_sensitive(self) -> None:
        cells: list[dict[str, object]] = [
            {"block": "coefficients", "label": "alpha", "value": "1"}
        ]
        assert attribution_result_hash(cells) == attribution_result_hash(cells)
        other: list[dict[str, object]] = [
            {"block": "coefficients", "label": "alpha", "value": "2"}
        ]
        assert attribution_result_hash(cells) != attribution_result_hash(other)

    def test_residual_digest_deterministic_and_series_sensitive(self) -> None:
        assert residual_digest(["0", "1", "-1"]) == residual_digest(["0", "1", "-1"])
        assert residual_digest(["0", "1", "-1"]) != residual_digest(["0", "1", "1"])

    def test_empty_residual_series_has_stable_digest(self) -> None:
        # The singular-design case digests the empty series — stable and distinct.
        assert residual_digest([]) == residual_digest([])
        assert residual_digest([]) != residual_digest(["0"])
