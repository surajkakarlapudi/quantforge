"""Tests for SEC URL construction and CIK canonicalization."""

from __future__ import annotations

import pytest

from openfinance.sec.endpoints import (
    canonical_cik,
    cik10,
    company_facts_url,
    company_tickers_url,
    filing_document_url,
    filing_index_url,
    submissions_page_url,
    submissions_url,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (320193, "320193"),
        ("320193", "320193"),
        ("0000320193", "320193"),
        ("CIK0000320193", "320193"),
        (" 0000320193 ", "320193"),
    ],
)
def test_canonical_cik(value: str | int, expected: str) -> None:
    assert canonical_cik(value) == expected


def test_cik10_zero_pads() -> None:
    assert cik10(320193) == "0000320193"
    assert cik10("0000320193") == "0000320193"


def test_invalid_cik_rejected() -> None:
    with pytest.raises(ValueError):
        canonical_cik("not-a-cik")


def test_submissions_url() -> None:
    assert (
        submissions_url(320193) == "https://data.sec.gov/submissions/CIK0000320193.json"
    )


def test_submissions_page_url() -> None:
    assert submissions_page_url("CIK0000320193-submissions-001.json") == (
        "https://data.sec.gov/submissions/CIK0000320193-submissions-001.json"
    )


def test_company_facts_url() -> None:
    assert company_facts_url(320193) == (
        "https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json"
    )


def test_company_tickers_url() -> None:
    # Served from www.sec.gov (Archives host), not the data JSON API host.
    assert company_tickers_url() == "https://www.sec.gov/files/company_tickers.json"


def test_filing_index_url_strips_accession_dashes() -> None:
    assert filing_index_url(320193, "0000320193-18-000145") == (
        "https://www.sec.gov/Archives/edgar/data/320193/000032019318000145/index.json"
    )


def test_filing_document_url() -> None:
    assert filing_document_url(320193, "0000320193-18-000145", "aapl-20180929.xml") == (
        "https://www.sec.gov/Archives/edgar/data/320193/"
        "000032019318000145/aapl-20180929.xml"
    )
