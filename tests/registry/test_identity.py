"""Filing/company identity: canonicalization and determinism (data-model §11)."""

from __future__ import annotations

import pytest

from quantforge.registry.errors import AccessionFormatError
from quantforge.registry.identity import (
    canonical_accession,
    cik_from_company_id,
    company_id,
    filing_id,
)


def test_dashed_accession_is_canonical() -> None:
    assert canonical_accession("0000320193-23-000106") == "0000320193-23-000106"


def test_undashed_accession_canonicalizes_to_dashed() -> None:
    assert canonical_accession("000032019323000106") == "0000320193-23-000106"


def test_accession_whitespace_stripped() -> None:
    assert canonical_accession("  0000320193-23-000106 ") == ("0000320193-23-000106")


@pytest.mark.parametrize(
    "bad",
    [
        "",
        "not-an-accession",
        "0000320193-23-00010",  # too short sequence
        "0000320193/23/000106",  # wrong separator
        "320193-23-000106",  # filer id not 10 digits
        "AAPL-23-000106",  # never derive identity from a ticker
    ],
)
def test_invalid_accession_rejected(bad: str) -> None:
    with pytest.raises(AccessionFormatError):
        canonical_accession(bad)


def test_company_id_zero_pads_to_ten_digits() -> None:
    assert company_id(320193) == "cik:0000320193"
    assert company_id("320193") == "cik:0000320193"
    assert company_id("0000320193") == "cik:0000320193"


def test_company_id_identical_across_string_and_int_cik() -> None:
    # submissions API gives a padded string; companyfacts gives an int.
    assert company_id("0000320193") == company_id(320193)


def test_filing_id_prefixes_canonical_accession() -> None:
    assert filing_id("000032019323000106") == ("accession:0000320193-23-000106")


def test_filing_id_is_deterministic() -> None:
    assert filing_id("0000320193-23-000106") == filing_id("0000320193-23-000106")


def test_cik_from_company_id_roundtrips() -> None:
    assert cik_from_company_id(company_id(320193)) == "320193"


def test_cik_from_company_id_rejects_non_company_id() -> None:
    with pytest.raises(ValueError, match="not a company_id"):
        cik_from_company_id("AAPL")
