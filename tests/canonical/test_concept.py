"""Concept preservation: no mapping, no merging, Clark identity retained."""

from __future__ import annotations

from quantforge.canonical.concept import concept_from_clark
from quantforge.canonical.taxonomy import Taxonomy


def test_gaap_concept_split_and_classified() -> None:
    c = concept_from_clark("{http://fasb.org/us-gaap/2023}Revenues")
    assert c.namespace_uri == "http://fasb.org/us-gaap/2023"
    assert c.local_name == "Revenues"
    assert c.taxonomy is Taxonomy.US_GAAP
    assert c.clark == "{http://fasb.org/us-gaap/2023}Revenues"


def test_similar_gaap_concepts_are_not_merged() -> None:
    # RevenueFromContractWithCustomerExcludingAssessedTax must remain distinct
    # from Revenues — no aggressive mapping (requirement 2).
    a = concept_from_clark("{http://fasb.org/us-gaap/2023}Revenues")
    b = concept_from_clark(
        "{http://fasb.org/us-gaap/2023}"
        "RevenueFromContractWithCustomerExcludingAssessedTax"
    )
    assert a.clark != b.clark
    assert a.local_name != b.local_name


def test_issuer_concept_preserved_intact() -> None:
    c = concept_from_clark("{http://apple.com/20230930}ProductRevenue")
    assert c.taxonomy is Taxonomy.CUSTOM
    assert c.local_name == "ProductRevenue"
    assert c.namespace_uri == "http://apple.com/20230930"


def test_unqualified_concept_has_no_namespace_and_unknown_taxonomy() -> None:
    c = concept_from_clark("BareLocalName")
    assert c.namespace_uri is None
    assert c.local_name == "BareLocalName"
    assert c.taxonomy is Taxonomy.UNKNOWN


def test_to_dict_round_trips_fields() -> None:
    c = concept_from_clark("{http://xbrl.sec.gov/dei/2023}EntityRegistrantName")
    d = c.to_dict()
    assert d == {
        "clark": "{http://xbrl.sec.gov/dei/2023}EntityRegistrantName",
        "namespace_uri": "http://xbrl.sec.gov/dei/2023",
        "local_name": "EntityRegistrantName",
        "taxonomy": "dei",
    }
