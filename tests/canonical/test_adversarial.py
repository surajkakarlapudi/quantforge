"""Adversarial information-loss tests for canonicalization (requirement 15).

Canonicalization must **never collapse distinct observations merely because they
look similar**. Each test below constructs facts that differ in exactly one
dimension of meaning and asserts the canonicalizer keeps them as distinct
:class:`Fact` records (distinct ``fact_id``) — while the *one* case where facts
are genuinely identical (a byte-level duplicate) collapses to a single Fact with
full provenance to both raw facts, and a *contradiction* fails closed.

The mandated minimum 15 cases (§15):

1.  same concept, different dimensions
2.  same concept, different periods
3.  same concept, different units
4.  nil vs zero
5.  different decimals
6.  different scale
7.  positive vs negative
8.  custom issuer concept vs us-gaap concept (same local name)
9.  same economic period across two filings
10. amendment vs original (different accession)
11. multiple dimensions in different ordering (same identity — must NOT split)
12. typed dimensions vs a different typed value
13. unknown units (two different unknown units must not merge)
14. unknown taxonomy (preserved, distinct from us-gaap)
15. duplicate raw facts (collapse to one Fact, both raw ids retained)
"""

from __future__ import annotations

import pytest

from openfinance.canonical.canonicalize import Canonicalizer
from openfinance.canonical.errors import CanonicalContradictionError
from openfinance.canonical.taxonomy import Taxonomy
from tests.xbrl.builders import Ctx, ExplicitDim, Fact, InstanceBuilder, TypedDim, Unit

from .builders import canonicalize, fact_ids, facts, parse

USD = Unit("usd", measures=["iso4217:USD"])


# 1. Same concept, different dimensions -------------------------------------


def test_case01_same_concept_different_dimensions_kept_distinct() -> None:
    b = (
        InstanceBuilder()
        .with_context(
            Ctx(
                "prod",
                instant="2023-09-30",
                segment=[
                    ExplicitDim("srt:ProductOrServiceAxis", "us-gaap:ProductMember")
                ],
            )
        )
        .with_context(
            Ctx(
                "svc",
                instant="2023-09-30",
                segment=[
                    ExplicitDim("srt:ProductOrServiceAxis", "us-gaap:ServiceMember")
                ],
            )
        )
        .with_unit(USD)
        .with_fact(Fact("us-gaap:Revenues", "prod", value="100", unit_ref="usd"))
        .with_fact(Fact("us-gaap:Revenues", "svc", value="100", unit_ref="usd"))
    )
    fs = facts(b)
    assert len(fs) == 2
    assert len(fact_ids(fs)) == 2
    assert fs[0].dimensions_hash != fs[1].dimensions_hash


# 2. Same concept, different periods ----------------------------------------


def test_case02_same_concept_different_periods_kept_distinct() -> None:
    b = (
        InstanceBuilder()
        .with_context(Ctx("q1", start="2022-10-01", end="2022-12-31"))
        .with_context(Ctx("q2", start="2023-01-01", end="2023-03-31"))
        .with_unit(USD)
        .with_fact(Fact("us-gaap:Revenues", "q1", value="100", unit_ref="usd"))
        .with_fact(Fact("us-gaap:Revenues", "q2", value="120", unit_ref="usd"))
    )
    fs = facts(b)
    assert len(fact_ids(fs)) == 2
    assert {(f.period_start, f.period_end) for f in fs} == {
        ("2022-10-01", "2022-12-31"),
        ("2023-01-01", "2023-03-31"),
    }


# 3. Same concept, different units ------------------------------------------


def test_case03_same_concept_different_units_kept_distinct() -> None:
    b = (
        InstanceBuilder()
        .with_context(Ctx("c1", instant="2023-09-30"))
        .with_unit(USD)
        .with_unit(Unit("eur", measures=["iso4217:EUR"]))
        .with_fact(Fact("us-gaap:CashAndEquiv", "c1", value="1", unit_ref="usd"))
        .with_fact(Fact("us-gaap:CashAndEquiv", "c1", value="1", unit_ref="eur"))
    )
    fs = facts(b)
    assert len(fact_ids(fs)) == 2
    assert {f.unit for f in fs} == {"USD", "EUR"}
    assert {f.currency for f in fs} == {"USD", "EUR"}


# 4. nil vs zero -------------------------------------------------------------


def test_case04_nil_versus_zero_kept_distinct() -> None:
    b = (
        InstanceBuilder()
        .with_context(Ctx("c1", instant="2023-09-30"))
        .with_context(Ctx("c2", instant="2022-09-30"))
        .with_unit(USD)
        .with_fact(Fact("us-gaap:Goodwill", "c1", unit_ref="usd", nil=True))
        .with_fact(Fact("us-gaap:Goodwill", "c2", value="0", unit_ref="usd"))
    )
    fs = facts(b)
    nil_fact = next(f for f in fs if f.is_nil)
    zero_fact = next(f for f in fs if not f.is_nil)
    assert nil_fact.value_numeric_str is None  # nil is never coerced to zero
    assert zero_fact.value_numeric_str == "0"
    assert nil_fact.fact_id != zero_fact.fact_id


# 5. Different decimals ------------------------------------------------------


def test_case05_different_decimals_both_preserved() -> None:
    # decimals is precision metadata; two facts differing only by decimals are
    # (per the raw layer) distinct raw facts disambiguated by ordinal, but they
    # canonicalize to the SAME obs_key + SAME value, so they COLLAPSE to one
    # Fact — and the collapse must not lose the fact that both existed.
    b = (
        InstanceBuilder()
        .with_context(Ctx("c1", instant="2023-09-30"))
        .with_unit(USD)
        .with_fact(
            Fact("us-gaap:Cash", "c1", value="100", unit_ref="usd", decimals="-6")
        )
        .with_fact(
            Fact("us-gaap:Cash", "c1", value="100", unit_ref="usd", decimals="-3")
        )
    )
    result = canonicalize(b)
    # Same value, same obs_key → one canonical Fact; both raw facts traced.
    assert result.fact_count == 1
    assert result.raw_fact_count == 2
    assert result.collapsed_duplicate_count == 1
    only = result.facts[0]
    assert len(only.provenance.raw_fact_ids) == 2


def test_case05b_different_decimals_but_different_value_kept_distinct() -> None:
    # If the *values* differ (not just the decimals), the two observations are
    # genuinely different and must stay distinct across two filings.
    b1 = (
        InstanceBuilder()
        .with_context(Ctx("c1", instant="2023-09-30"))
        .with_unit(USD)
        .with_fact(
            Fact("us-gaap:Cash", "c1", value="100", unit_ref="usd", decimals="-6")
        )
    )
    b2 = (
        InstanceBuilder()
        .with_context(Ctx("c1", instant="2023-09-30"))
        .with_unit(USD)
        .with_fact(
            Fact("us-gaap:Cash", "c1", value="101", unit_ref="usd", decimals="-3")
        )
    )
    f1 = facts(b1, accession="0000320193-23-000106")[0]
    f2 = facts(b2, accession="0000320193-24-000001")[0]
    assert f1.fact_id != f2.fact_id


# 6. Different scale ---------------------------------------------------------


def test_case06_different_scale_kept_distinct_and_folded_once() -> None:
    # Two filings report the same concept/period but with different scale, so the
    # canonical base-unit value differs (123 * 10^3 vs 123 * 10^0). Distinct.
    b_scaled = (
        InstanceBuilder()
        .with_context(Ctx("c1", instant="2023-09-30"))
        .with_unit(USD)
        .with_fact(Fact("us-gaap:Cash", "c1", value="123", unit_ref="usd", scale="3"))
    )
    b_plain = (
        InstanceBuilder()
        .with_context(Ctx("c1", instant="2023-09-30"))
        .with_unit(USD)
        .with_fact(Fact("us-gaap:Cash", "c1", value="123", unit_ref="usd"))
    )
    scaled = facts(b_scaled, accession="0000320193-23-000106")[0]
    plain = facts(b_plain, accession="0000320193-24-000001")[0]
    assert scaled.value_numeric_str == "123000"  # folded exactly once
    assert plain.value_numeric_str == "123"
    assert scaled.fact_id != plain.fact_id
    # Raw lexical value is retained verbatim regardless of the fold.
    assert scaled.raw_value == "123"
    assert scaled.raw_scale == "3"


# 7. Positive vs negative ----------------------------------------------------


def test_case07_positive_versus_negative_kept_distinct() -> None:
    b_pos = (
        InstanceBuilder()
        .with_context(Ctx("c1", instant="2023-09-30"))
        .with_unit(USD)
        .with_fact(Fact("us-gaap:NetIncomeLoss", "c1", value="500", unit_ref="usd"))
    )
    b_neg = (
        InstanceBuilder()
        .with_context(Ctx("c1", instant="2023-09-30"))
        .with_unit(USD)
        .with_fact(
            Fact("us-gaap:NetIncomeLoss", "c1", value="500", unit_ref="usd", sign="-")
        )
    )
    pos = facts(b_pos, accession="0000320193-23-000106")[0]
    neg = facts(b_neg, accession="0000320193-24-000001")[0]
    assert pos.value_numeric_str == "500"
    assert neg.value_numeric_str == "-500"  # sign folded exactly once
    assert pos.fact_id != neg.fact_id
    assert neg.raw_value == "500" and neg.raw_sign == "-"  # raw magnitude retained


# 8. Custom issuer concept vs us-gaap concept (same local name) --------------


def test_case08_custom_concept_versus_gaap_same_localname_kept_distinct() -> None:
    b = (
        InstanceBuilder()
        .with_ns("aapl", "http://apple.com/20230930")
        .with_context(Ctx("c1", instant="2023-09-30"))
        .with_unit(USD)
        .with_fact(Fact("us-gaap:Revenues", "c1", value="100", unit_ref="usd"))
        .with_fact(Fact("aapl:Revenues", "c1", value="100", unit_ref="usd"))
    )
    fs = facts(b)
    assert len(fact_ids(fs)) == 2  # local-name collision must NOT merge them
    taxonomies = {f.taxonomy for f in fs}
    assert taxonomies == {Taxonomy.US_GAAP, Taxonomy.CUSTOM}


# 9. Same economic period across two filings --------------------------------


def test_case09_same_period_across_filings_kept_distinct() -> None:
    # Identical concept/period/unit/value, but two different filings. Identity
    # includes filing_id, so they must be distinct Facts (no restatement
    # resolution in Phase 4 — both are kept).
    def build() -> InstanceBuilder:
        return (
            InstanceBuilder()
            .with_context(Ctx("c1", instant="2023-09-30"))
            .with_unit(USD)
            .with_fact(Fact("us-gaap:Cash", "c1", value="100", unit_ref="usd"))
        )

    f_orig = facts(build(), accession="0000320193-23-000106")[0]
    f_other = facts(build(), accession="0000320193-24-000001")[0]
    assert f_orig.value_numeric_str == f_other.value_numeric_str
    assert f_orig.fact_id != f_other.fact_id
    assert f_orig.filing_id != f_other.filing_id


# 10. Amendment vs original (different accession) ---------------------------


def test_case10_amendment_versus_original_kept_distinct() -> None:
    # An amendment (10-K/A) restates the same value; Phase 4 keeps both, keyed by
    # their distinct filing_id. Amendment status is a Phase 2 registry concern and
    # is not resolved here.
    def build() -> InstanceBuilder:
        return (
            InstanceBuilder()
            .with_context(Ctx("c1", instant="2023-09-30"))
            .with_unit(USD)
            .with_fact(Fact("us-gaap:Assets", "c1", value="1000", unit_ref="usd"))
        )

    original = facts(build(), accession="0000320193-23-000106")[0]
    amendment = facts(build(), accession="0000320193-23-000200")[0]
    assert original.fact_id != amendment.fact_id


# 11. Multiple dimensions, different ordering (same identity) ---------------


def test_case11_multiple_dimensions_reordered_do_not_split() -> None:
    # The SAME two dimensions in a different source order describe the SAME slice;
    # canonicalization must treat them as identical (dimensions_hash sorts), so
    # across two filings the obs_key matches. (Different filings → distinct
    # fact_id, but the obs_key and dimensions_hash must be equal.)
    b_ab = (
        InstanceBuilder()
        .with_context(
            Ctx(
                "c1",
                instant="2023-09-30",
                segment=[
                    ExplicitDim("srt:ProductOrServiceAxis", "us-gaap:ProductMember"),
                    ExplicitDim("srt:StatementGeographicalAxis", "us-gaap:USMember"),
                ],
            )
        )
        .with_unit(USD)
        .with_fact(Fact("us-gaap:Revenues", "c1", value="100", unit_ref="usd"))
    )
    b_ba = (
        InstanceBuilder()
        .with_context(
            Ctx(
                "c1",
                instant="2023-09-30",
                segment=[
                    ExplicitDim("srt:StatementGeographicalAxis", "us-gaap:USMember"),
                    ExplicitDim("srt:ProductOrServiceAxis", "us-gaap:ProductMember"),
                ],
            )
        )
        .with_unit(USD)
        .with_fact(Fact("us-gaap:Revenues", "c1", value="100", unit_ref="usd"))
    )
    f_ab = facts(b_ab, accession="0000320193-23-000106")[0]
    f_ba = facts(b_ba, accession="0000320193-23-000106")[0]
    assert f_ab.dimensions_hash == f_ba.dimensions_hash
    assert f_ab.obs_key == f_ba.obs_key
    assert f_ab.fact_id == f_ba.fact_id  # same filing + same obs_key


# 12. Typed dimensions -------------------------------------------------------


def test_case12_typed_dimensions_different_values_kept_distinct() -> None:
    b = (
        InstanceBuilder()
        .with_context(
            Ctx(
                "d1",
                instant="2023-09-30",
                segment=[TypedDim("us-gaap:ScheduleAxis", "us-gaap:Tranche", "A")],
            )
        )
        .with_context(
            Ctx(
                "d2",
                instant="2023-09-30",
                segment=[TypedDim("us-gaap:ScheduleAxis", "us-gaap:Tranche", "B")],
            )
        )
        .with_unit(USD)
        .with_fact(Fact("us-gaap:DebtInstrument", "d1", value="1", unit_ref="usd"))
        .with_fact(Fact("us-gaap:DebtInstrument", "d2", value="1", unit_ref="usd"))
    )
    fs = facts(b)
    assert len(fact_ids(fs)) == 2
    assert fs[0].dimensions_hash != fs[1].dimensions_hash
    assert all(d.is_typed for f in fs for d in f.dimensions)


# 13. Unknown units ----------------------------------------------------------


def test_case13_two_unknown_units_do_not_merge() -> None:
    # Two custom/unrecognized units both canonicalize to UNKNOWN, but their raw
    # structure differs — they must NOT collapse into one Fact.
    b = (
        InstanceBuilder()
        .with_ns("xx", "http://example.com/units")
        .with_context(Ctx("c1", instant="2023-09-30"))
        .with_unit(Unit("u1", measures=["xx:Widgets"]))
        .with_unit(Unit("u2", measures=["xx:Gadgets"]))
        .with_fact(Fact("us-gaap:ProductionVolume", "c1", value="5", unit_ref="u1"))
        .with_fact(Fact("us-gaap:ProductionVolume", "c1", value="5", unit_ref="u2"))
    )
    fs = facts(b)
    assert len(fact_ids(fs)) == 2  # UNKNOWN units keyed by raw structural ref
    assert {f.unit for f in fs} == {"UNKNOWN"}
    assert all(f.currency is None for f in fs)


# 14. Unknown taxonomy -------------------------------------------------------


def test_case14_unknown_taxonomy_preserved_and_distinct() -> None:
    b = (
        InstanceBuilder()
        .with_ns("foo", "http://foo.example/custom/2023")
        .with_context(Ctx("c1", instant="2023-09-30"))
        .with_unit(USD)
        .with_fact(Fact("us-gaap:Revenues", "c1", value="100", unit_ref="usd"))
        .with_fact(Fact("foo:SpecialMetric", "c1", value="100", unit_ref="usd"))
    )
    fs = facts(b)
    assert len(fact_ids(fs)) == 2
    by_tax = {f.taxonomy for f in fs}
    assert Taxonomy.US_GAAP in by_tax
    assert Taxonomy.CUSTOM in by_tax  # namespaced-but-unrecognized → CUSTOM, kept
    custom = next(f for f in fs if f.taxonomy is Taxonomy.CUSTOM)
    assert custom.concept.namespace_uri == "http://foo.example/custom/2023"


# 15. Duplicate raw facts ----------------------------------------------------


def test_case15_duplicate_raw_facts_collapse_but_retain_both() -> None:
    # Byte-level duplicate (same concept/context/unit/value, disambiguated only by
    # ordinal in the raw layer) collapses to ONE canonical Fact, and both raw ids
    # are retained in provenance so nothing is silently dropped.
    b = (
        InstanceBuilder()
        .with_context(Ctx("c1", instant="2023-09-30"))
        .with_unit(USD)
        .with_fact(Fact("us-gaap:Cash", "c1", value="100", unit_ref="usd"))
        .with_fact(Fact("us-gaap:Cash", "c1", value="100", unit_ref="usd"))
    )
    result = canonicalize(b)
    assert result.raw_fact_count == 2
    assert result.fact_count == 1
    assert result.collapsed_duplicate_count == 1
    only = result.facts[0]
    assert len(only.provenance.raw_fact_ids) == 2
    # The representative raw fact is one of the contributing raw facts, and the
    # full set of contributing raw ids is retained (sorted) so neither is lost.
    assert only.provenance.raw_fact_id in only.provenance.raw_fact_ids
    assert only.provenance.raw_fact_ids == tuple(sorted(only.provenance.raw_fact_ids))


def test_contradiction_same_obs_key_different_value_fails_closed() -> None:
    # Same obs_key within one filing but DIFFERENT canonical value is a
    # data-quality contradiction — we must fail closed, never arbitrate.
    b = (
        InstanceBuilder()
        .with_context(Ctx("c1", instant="2023-09-30"))
        .with_unit(USD)
        .with_fact(Fact("us-gaap:Cash", "c1", value="100", unit_ref="usd"))
        .with_fact(Fact("us-gaap:Cash", "c1", value="101", unit_ref="usd"))
    )
    parsed = parse(b)
    with pytest.raises(CanonicalContradictionError):
        Canonicalizer().canonicalize(parsed)


# Precision variants (data-model open-question 8, resolved: prefer most-precise)
# ---------------------------------------------------------------------------
#
# Real SEC filings report the SAME economic value twice at different `decimals`
# precision (observed on Apple/Tesla/Berkshire: UnrecognizedTaxBenefits as
# 23,242,000,000 @ -6 and 23,200,000,000 @ -8). Per the resolved policy these
# collapse to the MOST-PRECISE value; a value that is NOT a consistent rounding
# still fails closed.


def test_precision_variants_collapse_to_most_precise() -> None:
    # 23,242,000,000 (decimals=-6) and its rounding to the nearest 10^8,
    # 23,200,000,000 (decimals=-8), are the same figure at two precisions. They
    # collapse to ONE Fact carrying the most-precise value; both raw ids survive.
    b = (
        InstanceBuilder()
        .with_context(Ctx("c1", instant="2023-09-30"))
        .with_unit(USD)
        .with_fact(
            Fact(
                "us-gaap:UnrecognizedTaxBenefits",
                "c1",
                value="23242000000",
                unit_ref="usd",
                decimals="-6",
            )
        )
        .with_fact(
            Fact(
                "us-gaap:UnrecognizedTaxBenefits",
                "c1",
                value="23200000000",
                unit_ref="usd",
                decimals="-8",
            )
        )
    )
    result = canonicalize(b)
    assert result.fact_count == 1
    assert result.raw_fact_count == 2
    assert result.collapsed_duplicate_count == 1
    only = result.facts[0]
    assert only.value_numeric_str == "23242000000"  # most-precise wins
    assert only.raw_decimals == "-6"
    assert len(only.provenance.raw_fact_ids) == 2  # nothing dropped


def test_precision_variants_order_independent() -> None:
    # The most-precise value wins regardless of source order (determinism).
    b = (
        InstanceBuilder()
        .with_context(Ctx("c1", instant="2023-09-30"))
        .with_unit(USD)
        .with_fact(
            Fact(
                "us-gaap:Assets",
                "c1",
                value="23200000000",
                unit_ref="usd",
                decimals="-8",
            )
        )
        .with_fact(
            Fact(
                "us-gaap:Assets",
                "c1",
                value="23242000000",
                unit_ref="usd",
                decimals="-6",
            )
        )
    )
    only = facts(b)[0]
    assert only.value_numeric_str == "23242000000"


def test_inconsistent_rounding_still_fails_closed() -> None:
    # 23,242,000,000 rounded to the nearest 10^8 is 23,200,000,000, NOT
    # 23,300,000,000 — so this pair is a genuine contradiction, not a precision
    # variant, and must fail closed.
    b = (
        InstanceBuilder()
        .with_context(Ctx("c1", instant="2023-09-30"))
        .with_unit(USD)
        .with_fact(
            Fact(
                "us-gaap:Cash", "c1", value="23242000000", unit_ref="usd", decimals="-6"
            )
        )
        .with_fact(
            Fact(
                "us-gaap:Cash", "c1", value="23300000000", unit_ref="usd", decimals="-8"
            )
        )
    )
    parsed = parse(b)
    with pytest.raises(CanonicalContradictionError):
        Canonicalizer().canonicalize(parsed)


def test_precision_variant_missing_decimals_fails_closed() -> None:
    # If one member has no readable `decimals`, no rounding relationship can be
    # established between differing values — fail closed rather than guess.
    b = (
        InstanceBuilder()
        .with_context(Ctx("c1", instant="2023-09-30"))
        .with_unit(USD)
        .with_fact(
            Fact(
                "us-gaap:Cash", "c1", value="23242000000", unit_ref="usd", decimals="-6"
            )
        )
        .with_fact(Fact("us-gaap:Cash", "c1", value="23200000000", unit_ref="usd"))
    )
    parsed = parse(b)
    with pytest.raises(CanonicalContradictionError):
        Canonicalizer().canonicalize(parsed)
