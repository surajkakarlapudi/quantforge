"""Tests for the Phase 9.2 :class:`UniverseSpecification` and the filter framework.

These are the pure, offline tests: filter identity/declaration, specification
validation and content-addressing, and serialization round trips. The
resolver-and-metric-driven build behaviour lives in ``test_builder.py`` against a
real backend.
"""

from __future__ import annotations

import pytest

from quantforge.metrics.model import MetricPeriod
from quantforge.universe.errors import UniverseSpecificationError
from quantforge.universe.filters import (
    CompanyMetricFilter,
    ComparisonOperator,
    ExplicitCompanyFilter,
    FilterKind,
    SectorClassification,
    SectorFilter,
    filter_from_dict,
)
from quantforge.universe.specification import (
    SPECIFICATION_VERSION,
    UniverseSpecification,
)

PERIOD = MetricPeriod.instant("2023-09-30")


def _explicit(*ids: str) -> ExplicitCompanyFilter:
    return ExplicitCompanyFilter(identifiers=tuple(ids))


def _metric(threshold: str = "0") -> CompanyMetricFilter:
    return CompanyMetricFilter(
        metric_key="working_capital",
        period=PERIOD,
        operator=ComparisonOperator.GT,
        threshold=threshold,
    )


# -- filter identity & declaration ------------------------------------------


def test_filter_id_is_sha256_prefixed_and_stable() -> None:
    a = _explicit("AAPL", "MSFT")
    b = _explicit("AAPL", "MSFT")
    assert a.filter_id.startswith("sha256:")
    assert a.filter_id == b.filter_id


def test_filter_id_is_order_sensitive() -> None:
    assert _explicit("AAPL", "MSFT").filter_id != _explicit("MSFT", "AAPL").filter_id


def test_filter_id_changes_with_parameters() -> None:
    assert _metric("0").filter_id != _metric("100").filter_id
    lt = CompanyMetricFilter(
        metric_key="working_capital",
        period=PERIOD,
        operator=ComparisonOperator.LT,
        threshold="0",
    )
    assert lt.filter_id != _metric("0").filter_id


def test_explicit_is_source_others_are_not() -> None:
    assert _explicit("AAPL").is_source
    assert not _metric().is_source
    assert not SectorFilter(scheme="gics", sector="Technology").is_source


def test_filter_kinds() -> None:
    assert _explicit("AAPL").kind is FilterKind.EXPLICIT
    assert _metric().kind is FilterKind.METRIC
    assert SectorFilter(scheme="gics", sector="Tech").kind is FilterKind.SECTOR


# -- filter serialization round trips ---------------------------------------


def test_explicit_filter_round_trips() -> None:
    f = ExplicitCompanyFilter(identifiers=("AAPL", "MSFT"), by="ticker")
    back = filter_from_dict(f.to_dict())
    assert isinstance(back, ExplicitCompanyFilter)
    assert back == f
    assert back.filter_id == f.filter_id


def test_metric_filter_round_trips() -> None:
    f = _metric("123.45")
    back = filter_from_dict(f.to_dict())
    assert isinstance(back, CompanyMetricFilter)
    assert back == f
    assert back.filter_id == f.filter_id


def test_sector_filter_round_trips() -> None:
    f = SectorFilter(scheme="gics", sector="Technology", operator=ComparisonOperator.NE)
    back = filter_from_dict(f.to_dict())
    assert isinstance(back, SectorFilter)
    assert back == f
    assert back.filter_id == f.filter_id


def test_filter_from_dict_rejects_unknown_kind() -> None:
    with pytest.raises(UniverseSpecificationError, match="unknown filter kind"):
        filter_from_dict({"kind": "bogus"})


def test_filter_from_dict_rejects_missing_kind() -> None:
    with pytest.raises(UniverseSpecificationError, match="missing a string 'kind'"):
        filter_from_dict({"identifiers": ["AAPL"]})


def test_metric_filter_from_dict_rejects_bad_period() -> None:
    raw = _metric().to_dict()
    raw["period"] = "not-an-object"
    with pytest.raises(UniverseSpecificationError, match="period"):
        filter_from_dict(raw)


# -- specification validation -----------------------------------------------


def test_specification_id_is_sha256_prefixed_and_stable() -> None:
    a = UniverseSpecification(name="tech", filters=(_explicit("AAPL"), _metric()))
    b = UniverseSpecification(name="tech", filters=(_explicit("AAPL"), _metric()))
    assert a.specification_id.startswith("sha256:")
    assert a.specification_id == b.specification_id


def test_specification_id_depends_on_name() -> None:
    a = UniverseSpecification(name="tech", filters=(_explicit("AAPL"),))
    b = UniverseSpecification(name="banks", filters=(_explicit("AAPL"),))
    assert a.specification_id != b.specification_id


def test_specification_id_is_filter_order_sensitive() -> None:
    a = UniverseSpecification(
        name="s", filters=(_explicit("AAPL", "MSFT"), _metric("0"), _metric("1"))
    )
    b = UniverseSpecification(
        name="s", filters=(_explicit("AAPL", "MSFT"), _metric("1"), _metric("0"))
    )
    assert a.specification_id != b.specification_id


def test_empty_filters_fails_closed() -> None:
    with pytest.raises(UniverseSpecificationError, match="at least one filter"):
        UniverseSpecification(name="s", filters=())


def test_empty_name_fails_closed() -> None:
    with pytest.raises(UniverseSpecificationError, match="non-empty name"):
        UniverseSpecification(name="", filters=(_explicit("AAPL"),))


def test_narrowing_filter_first_fails_closed() -> None:
    with pytest.raises(UniverseSpecificationError, match="first filter must be"):
        UniverseSpecification(name="s", filters=(_metric(),))


def test_sector_filter_first_fails_closed() -> None:
    with pytest.raises(UniverseSpecificationError, match="first filter must be"):
        UniverseSpecification(
            name="s", filters=(SectorFilter(scheme="gics", sector="Tech"),)
        )


def test_default_spec_version_is_pinned() -> None:
    spec = UniverseSpecification(name="s", filters=(_explicit("AAPL"),))
    assert spec.spec_version == SPECIFICATION_VERSION


# -- specification serialization round trip ---------------------------------


def test_specification_round_trips() -> None:
    spec = UniverseSpecification(
        name="large-cap-tech",
        filters=(
            ExplicitCompanyFilter(identifiers=("AAPL", "MSFT", "NVDA")),
            _metric("1000000"),
            SectorFilter(scheme="gics", sector="Technology"),
        ),
    )
    back = UniverseSpecification.from_dict(spec.to_dict())
    assert back.name == spec.name
    assert back.spec_version == spec.spec_version
    assert back.filter_ids == spec.filter_ids
    assert back.specification_id == spec.specification_id


def test_specification_from_dict_revalidates() -> None:
    # A tampered serialization with a narrowing filter first must not reconstruct.
    raw: dict[str, object] = {
        "name": "s",
        "spec_version": SPECIFICATION_VERSION,
        "filters": [_metric().to_dict()],
    }
    with pytest.raises(UniverseSpecificationError):
        UniverseSpecification.from_dict(raw)


def test_specification_to_dict_is_serializable() -> None:
    spec = UniverseSpecification(name="s", filters=(_explicit("AAPL"), _metric()))
    record = spec.to_dict()
    assert record["specification_id"] == spec.specification_id
    assert record["name"] == "s"
    filters = record["filters"]
    assert isinstance(filters, list)
    assert filters[0]["kind"] == "explicit"


# -- comparison operators ----------------------------------------------------


def test_comparison_operator_decimal_semantics() -> None:
    from decimal import Decimal

    assert ComparisonOperator.GT.compare_decimal(Decimal(2), Decimal(1))
    assert not ComparisonOperator.GT.compare_decimal(Decimal(1), Decimal(1))
    assert ComparisonOperator.GE.compare_decimal(Decimal(1), Decimal(1))
    assert ComparisonOperator.EQ.compare_decimal(Decimal("2.0"), Decimal(2))


def test_comparison_operator_sector_semantics() -> None:
    assert ComparisonOperator.EQ.compare_sector("Tech", "Tech")
    assert ComparisonOperator.NE.compare_sector("Tech", "Banks")
    with pytest.raises(UniverseSpecificationError):
        ComparisonOperator.GT.compare_sector("Tech", "Tech")


# -- sector classification ---------------------------------------------------


def test_sector_classification_id_is_order_independent() -> None:
    a = SectorClassification(scheme="gics", assignments={"cik:1": "T", "cik:2": "B"})
    b = SectorClassification(scheme="gics", assignments={"cik:2": "B", "cik:1": "T"})
    assert a.classification_id == b.classification_id


def test_sector_classification_id_depends_on_scheme() -> None:
    a = SectorClassification(scheme="gics", assignments={"cik:1": "T"})
    b = SectorClassification(scheme="sic", assignments={"cik:1": "T"})
    assert a.classification_id != b.classification_id


def test_sector_classification_lookup() -> None:
    c = SectorClassification(
        scheme="gics", assignments={"cik:0000320193": "Technology"}
    )
    assert c.sector_of("cik:0000320193") == "Technology"
    assert c.sector_of("cik:0000000001") is None
