"""Taxonomy classification: by namespace URI, never prefix; never a closed set."""

from __future__ import annotations

import pytest

from openfinance.canonical.taxonomy import Taxonomy, classify_taxonomy


@pytest.mark.parametrize(
    ("uri", "expected"),
    [
        ("http://fasb.org/us-gaap/2023", Taxonomy.US_GAAP),
        ("http://fasb.org/us-gaap/2024-01-31", Taxonomy.US_GAAP),
        ("http://xbrl.us/us-gaap/2009-01-31", Taxonomy.US_GAAP),
        ("http://xbrl.sec.gov/dei/2023", Taxonomy.DEI),
        ("http://xbrl.us/dei/2009", Taxonomy.DEI),
        ("http://fasb.org/srt/2023", Taxonomy.SRT),
        ("http://xbrl.sec.gov/srt/2023", Taxonomy.SRT),
        ("http://xbrl.ifrs.org/taxonomy/2023-03-23/ifrs-full", Taxonomy.IFRS_FULL),
        ("https://xbrl.ifrs.org/taxonomy/2023-03-23/ifrs-full", Taxonomy.IFRS_FULL),
    ],
)
def test_standard_taxonomies_recognized_by_stem(uri: str, expected: Taxonomy) -> None:
    assert classify_taxonomy(uri) is expected


def test_issuer_extension_namespace_is_custom_not_rejected() -> None:
    # A company-specific extension must be preserved, never rejected (req. 3).
    assert classify_taxonomy("http://apple.com/20230930") is Taxonomy.CUSTOM
    assert classify_taxonomy("http://www.tesla.com/20231231") is Taxonomy.CUSTOM


def test_unrecognized_but_namespaced_is_custom() -> None:
    assert classify_taxonomy("http://example.org/whatever") is Taxonomy.CUSTOM


def test_missing_namespace_is_unknown_never_guessed() -> None:
    assert classify_taxonomy(None) is Taxonomy.UNKNOWN
    assert classify_taxonomy("") is Taxonomy.UNKNOWN


def test_classification_is_by_uri_not_prefix() -> None:
    # A URI that merely mentions "us-gaap" in a foreign host is NOT us-gaap; the
    # stems are anchored on the publisher host.
    assert classify_taxonomy("http://evil.example/us-gaap/2023") is Taxonomy.CUSTOM
