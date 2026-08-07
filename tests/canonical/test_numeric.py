"""Safe numeric handling: exact Decimal, scale/sign folded once, nil ≠ zero."""

from __future__ import annotations

from decimal import Decimal

import pytest

from quantforge.canonical.errors import CanonicalError
from quantforge.canonical.numeric import (
    canonical_decimal_str,
    canonicalize_numeric,
)
from quantforge.sec.artifacts import ArtifactType
from quantforge.xbrl.model import RawFact, RawFactProvenance

_PROV = RawFactProvenance(
    filing_id="accession:0000320193-23-000106",
    accession="0000320193-23-000106",
    company_id="cik:0000320193",
    source_artifact_sha256="0" * 64,
    source_artifact_type=ArtifactType.XBRL_INSTANCE,
    source_url="https://example.test/x.xml",
    source_document_name="x.xml",
    transformation_version_id="sha256:deadbeef",
)


def _raw(
    *,
    value_raw: str | None = None,
    is_nil: bool = False,
    scale: str | None = None,
    sign: str | None = None,
    decimals: str | None = None,
) -> RawFact:
    numeric = None
    if not is_nil and value_raw is not None:
        try:
            parsed = Decimal(value_raw)
            numeric = str(parsed) if parsed.is_finite() else None
        except Exception:
            numeric = None
    return RawFact(
        raw_fact_id="rf",
        raw_document_id="sha256:doc",
        concept="{http://fasb.org/us-gaap/2023}Cash",
        context_ref="c1",
        unit_ref="{http://www.xbrl.org/2003/iso4217}USD",
        dimensions_hash="sha256:dim",
        ordinal=0,
        value_raw=value_raw,
        value_numeric_str=numeric,
        is_nil=is_nil,
        decimals=decimals,
        scale=scale,
        sign=sign,
        provenance=_PROV,
    )


# -- canonical_decimal_str ---------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (Decimal("0"), "0"),
        (Decimal("-0"), "0"),  # negative zero normalized
        (Decimal("123"), "123"),
        (Decimal("123.4500"), "123.45"),  # trailing zeros stripped
        (Decimal("100.000"), "100"),
        (Decimal("-500"), "-500"),
        (Decimal("1E+3"), "1000"),  # never scientific notation
        (Decimal("0.00010"), "0.0001"),
    ],
)
def test_canonical_decimal_str_deterministic(value: Decimal, expected: str) -> None:
    assert canonical_decimal_str(value) == expected


# -- nil ---------------------------------------------------------------------


def test_nil_is_never_zero() -> None:
    n = canonicalize_numeric(_raw(is_nil=True))
    assert n.value_numeric_str is None
    assert n.value_text is None


# -- scale -------------------------------------------------------------------


def test_scale_folded_exactly_once() -> None:
    # value=123 scale=3 → 123000, NOT 123 nor 123000000 (the specific req. 8 test).
    n = canonicalize_numeric(_raw(value_raw="123", scale="3"))
    assert n.value_numeric_str == "123000"
    assert n.scale == 3


def test_default_scale_is_zero() -> None:
    n = canonicalize_numeric(_raw(value_raw="123"))
    assert n.value_numeric_str == "123"
    assert n.scale == 0


def test_negative_scale_divides() -> None:
    n = canonicalize_numeric(_raw(value_raw="4500", scale="-2"))
    assert n.value_numeric_str == "45"


def test_uninterpretable_scale_fails_closed() -> None:
    with pytest.raises(CanonicalError, match="uninterpretable scale"):
        canonicalize_numeric(_raw(value_raw="123", scale="abc"))


# -- sign --------------------------------------------------------------------


def test_sign_folded_exactly_once() -> None:
    n = canonicalize_numeric(_raw(value_raw="500", sign="-"))
    assert n.value_numeric_str == "-500"


def test_scale_and_sign_combined() -> None:
    n = canonicalize_numeric(_raw(value_raw="123", scale="3", sign="-"))
    assert n.value_numeric_str == "-123000"


def test_unsupported_sign_fails_closed() -> None:
    with pytest.raises(CanonicalError, match="unsupported sign"):
        canonicalize_numeric(_raw(value_raw="1", sign="+"))


# -- decimals ----------------------------------------------------------------


def test_decimals_parsed() -> None:
    n = canonicalize_numeric(_raw(value_raw="1", decimals="-6"))
    assert n.decimals == -6


def test_decimals_inf_degrades_to_none() -> None:
    n = canonicalize_numeric(_raw(value_raw="1", decimals="INF"))
    assert n.decimals is None


def test_decimals_absent_is_none() -> None:
    n = canonicalize_numeric(_raw(value_raw="1"))
    assert n.decimals is None


# -- non-numeric -------------------------------------------------------------


def test_non_numeric_value_preserved_as_text() -> None:
    n = canonicalize_numeric(_raw(value_raw="Large accelerated filer"))
    assert n.value_numeric_str is None
    assert n.value_text == "Large accelerated filer"


def test_large_and_small_values_exact() -> None:
    big = canonicalize_numeric(_raw(value_raw="123456789012345678"))
    assert big.value_numeric_str == "123456789012345678"
    small = canonicalize_numeric(_raw(value_raw="0.000001"))
    assert small.value_numeric_str == "0.000001"
