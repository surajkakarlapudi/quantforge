"""Transformation version: deterministic id, config-sensitive, code-sensitive."""

from __future__ import annotations

from openfinance.canonical.version import (
    CANONICAL_FACT_VERSION,
    CanonicalFactVersion,
)


def test_version_id_is_deterministic() -> None:
    assert (
        CanonicalFactVersion().transformation_version_id
        == CanonicalFactVersion().transformation_version_id
    )


def test_version_id_is_sha256_prefixed() -> None:
    assert CanonicalFactVersion().transformation_version_id.startswith("sha256:")


def test_default_code_version() -> None:
    assert CanonicalFactVersion().code_version == CANONICAL_FACT_VERSION


def test_different_code_version_changes_id() -> None:
    a = CanonicalFactVersion(code_version="canonical-fact/1")
    b = CanonicalFactVersion(code_version="canonical-fact/2")
    assert a.transformation_version_id != b.transformation_version_id


def test_different_config_changes_id() -> None:
    a = CanonicalFactVersion.for_config(b"")
    b = CanonicalFactVersion.for_config(b"unit-map-v2")
    assert a.transformation_version_id != b.transformation_version_id


def test_for_config_defaults_to_current_code_version() -> None:
    assert CanonicalFactVersion.for_config(b"x").code_version == CANONICAL_FACT_VERSION
