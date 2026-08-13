"""The declarative MinTRL request (§14): validation + canonicalization."""

from __future__ import annotations

from decimal import Decimal

import pytest

from quantforge.mintrl.errors import MinTrlConfigurationError
from quantforge.mintrl.spec import MinimumTrackRecordLengthSpecification
from quantforge.mintrl.version import MINTRL_SPEC_VERSION


def _spec(**overrides: object) -> MinimumTrackRecordLengthSpecification:
    base: dict[str, object] = {
        "name": "mintrl",
        "source_campaign_id": "sha256:src",
    }
    base.update(overrides)
    return MinimumTrackRecordLengthSpecification(**base)  # type: ignore[arg-type]


def test_default_spec_version_and_parameters() -> None:
    spec = _spec()
    assert spec.spec_version == MINTRL_SPEC_VERSION
    assert spec.confidence == "0.95"
    assert spec.benchmark_sharpe == "0"


def test_to_dict_is_the_canonical_request() -> None:
    assert _spec().to_dict() == {
        "spec_version": MINTRL_SPEC_VERSION,
        "name": "mintrl",
        "source_campaign_id": "sha256:src",
        "confidence": "0.95",
        "benchmark_sharpe": "0",
    }


def test_numeric_parameters_are_canonicalized() -> None:
    # A whitespace-padded / leading-zero spelling collapses to its canonical decimal
    # string.
    spec = _spec(confidence="0.950", benchmark_sharpe="+0.10")
    assert Decimal(spec.confidence) == Decimal("0.95")
    assert Decimal(spec.benchmark_sharpe) == Decimal("0.1")
    # The canonical string is fold-stable: re-declaring yields byte-identical
    # parameters.
    assert _spec(confidence="0.950").confidence == spec.confidence


def test_empty_name_is_rejected() -> None:
    with pytest.raises(MinTrlConfigurationError):
        _spec(name="")


def test_empty_source_id_is_rejected() -> None:
    with pytest.raises(MinTrlConfigurationError):
        _spec(source_campaign_id="")


def test_empty_spec_version_is_rejected() -> None:
    with pytest.raises(MinTrlConfigurationError):
        _spec(spec_version="")


def test_confidence_outside_open_unit_interval_is_rejected() -> None:
    for bad in ("0", "1", "1.5", "-0.1"):
        with pytest.raises(MinTrlConfigurationError):
            _spec(confidence=bad)


def test_non_decimal_confidence_is_rejected() -> None:
    with pytest.raises(MinTrlConfigurationError):
        _spec(confidence="not-a-number")


def test_non_finite_benchmark_is_rejected() -> None:
    for bad in ("NaN", "Infinity", "-Infinity"):
        with pytest.raises(MinTrlConfigurationError):
            _spec(benchmark_sharpe=bad)


def test_negative_benchmark_is_accepted() -> None:
    # A benchmark Sharpe may legitimately be zero or negative.
    assert _spec(benchmark_sharpe="-0.2").benchmark_sharpe == "-0.2"


def test_spec_is_frozen() -> None:
    spec = _spec()
    with pytest.raises(AttributeError):
        spec.name = "other"  # type: ignore[misc]
