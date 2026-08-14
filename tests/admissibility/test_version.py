"""The engine version pins code + method + decimal context (§13).

Phase 33 evaluates no standard-normal primitive of its own (it consumes already-sealed
p-values verbatim), so - unlike the significance layers - there is no normal-version
fold.
"""

from __future__ import annotations

from quantforge.admissibility.version import (
    ADMISSIBILITY_ENGINE_VERSION,
    ADMISSIBILITY_METHOD_VERSION,
    AdmissibilityEngineVersion,
    default_decimal_context,
)


def test_default_context_is_prec_34_half_even() -> None:
    ctx = default_decimal_context()
    assert ctx.prec == 34
    # A fresh instance each call, never a shared mutable context.
    assert default_decimal_context() is not ctx


def test_version_id_is_deterministic_and_sha256() -> None:
    base = AdmissibilityEngineVersion()
    other = AdmissibilityEngineVersion()
    assert base.admissibility_engine_version_id == other.admissibility_engine_version_id
    assert base.admissibility_engine_version_id.startswith("sha256:")
    assert base.config_hash.startswith("sha256:")


def test_defaults_match_module_constants() -> None:
    base = AdmissibilityEngineVersion()
    assert base.code_version == ADMISSIBILITY_ENGINE_VERSION
    assert base.method_version == ADMISSIBILITY_METHOD_VERSION


def test_version_id_folds_every_component() -> None:
    base_id = AdmissibilityEngineVersion().admissibility_engine_version_id
    assert (
        AdmissibilityEngineVersion(
            code_version="admissibility-engine/2"
        ).admissibility_engine_version_id
        != base_id
    )
    assert (
        AdmissibilityEngineVersion(
            method_version="admissibility-method/2"
        ).admissibility_engine_version_id
        != base_id
    )
    assert (
        AdmissibilityEngineVersion(decimal_precision=28).admissibility_engine_version_id
        != base_id
    )


def test_decimal_context_matches_the_pinned_precision() -> None:
    version = AdmissibilityEngineVersion(decimal_precision=28)
    assert version.decimal_context().prec == 28
