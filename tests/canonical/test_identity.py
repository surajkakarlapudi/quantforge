"""Fact identity (§11): includes transformation version, excludes raw_fact_id."""

from __future__ import annotations

from openfinance.canonical.model import fact_id, obs_key


def _key(**overrides: object) -> str:
    base: dict[str, object] = {
        "company_id": "cik:0000320193",
        "security_id": None,
        "concept_clark": "{http://fasb.org/us-gaap/2023}Cash",
        "period_type": "instant",
        "period_start": None,
        "period_end": "2023-09-30",
        "unit_ref": "{http://www.xbrl.org/2003/iso4217}USD",
        "dimensions_hash": "sha256:dim",
    }
    base.update(overrides)
    return obs_key(**base)  # type: ignore[arg-type]


def test_obs_key_is_deterministic() -> None:
    assert _key() == _key()


def test_obs_key_distinguishes_every_component() -> None:
    baseline = _key()
    assert _key(company_id="cik:0000000001") != baseline
    assert _key(concept_clark="{http://fasb.org/us-gaap/2023}Revenues") != baseline
    assert _key(period_end="2022-09-30") != baseline
    assert _key(unit_ref="{http://www.xbrl.org/2003/iso4217}EUR") != baseline
    assert _key(dimensions_hash="sha256:other") != baseline


def test_obs_key_uses_clark_concept_not_taxonomy_label() -> None:
    # Two issuer concepts with the same local name but different namespaces must
    # not produce the same obs_key.
    a = _key(concept_clark="{http://apple.com/2023}Revenue")
    b = _key(concept_clark="{http://tesla.com/2023}Revenue")
    assert a != b


def test_fact_id_is_sha256_prefixed_and_deterministic() -> None:
    fid = fact_id(
        transformation_version_id="sha256:tv",
        filing_id="accession:0000320193-23-000106",
        obs_key_value=_key(),
    )
    assert fid.startswith("sha256:")
    assert fid == fact_id(
        transformation_version_id="sha256:tv",
        filing_id="accession:0000320193-23-000106",
        obs_key_value=_key(),
    )


def test_fact_id_includes_transformation_version() -> None:
    # A new normalizer version yields a NEW fact_id (old Fact retained) — the
    # opposite of the parser-version-independent raw_fact_id (requirement 11).
    key = _key()
    v1 = fact_id(
        transformation_version_id="sha256:v1",
        filing_id="accession:0000320193-23-000106",
        obs_key_value=key,
    )
    v2 = fact_id(
        transformation_version_id="sha256:v2",
        filing_id="accession:0000320193-23-000106",
        obs_key_value=key,
    )
    assert v1 != v2


def test_fact_id_includes_filing() -> None:
    key = _key()
    a = fact_id(
        transformation_version_id="sha256:v1",
        filing_id="accession:0000320193-23-000106",
        obs_key_value=key,
    )
    b = fact_id(
        transformation_version_id="sha256:v1",
        filing_id="accession:0000320193-24-000001",
        obs_key_value=key,
    )
    assert a != b
