"""End-to-end registry build, query, pagination, determinism, and rebuild."""

from __future__ import annotations

from pathlib import Path

import pytest

from openfinance.registry.errors import SourceValidationError
from openfinance.registry.registry import FilingRegistry
from openfinance.registry.store import RegistryStore
from openfinance.registry.version import TransformationVersion

from .builders import FilingRow, SubmissionsBuilder

CIK = 320193


def _registry(tmp_path: Path, **kw: object) -> FilingRegistry:
    return FilingRegistry(RegistryStore(tmp_path / "registry"), **kw)  # type: ignore[arg-type]


def _sample_builder() -> SubmissionsBuilder:
    return (
        SubmissionsBuilder(CIK)
        .add(
            FilingRow(
                accession="0000320193-23-000106",
                form="10-K",
                filing_date="2023-11-03",
                report_date="2023-09-30",
                acceptance="2023-11-03T18:01:14.000Z",
                primary_document="aapl-20230930.htm",
            )
        )
        .add(
            FilingRow(
                accession="0000320193-23-000077",
                form="10-Q",
                filing_date="2023-08-04",
                report_date="2023-07-01",
                acceptance="2023-08-04T18:04:00.000Z",
            )
        )
        .add(
            FilingRow(
                accession="0000320193-22-000108",
                form="8-K",
                filing_date="2022-10-27",
                acceptance="2022-10-27T16:31:00.000Z",
            )
        )
    )


def test_build_and_list_filings(tmp_path: Path) -> None:
    reg = _registry(tmp_path)
    reg.build_company_from_artifacts([_sample_builder().primary_artifact()])
    filings = reg.list_filings(CIK)
    assert [f.accession_number for f in filings] == [
        "0000320193-22-000108",
        "0000320193-23-000077",
        "0000320193-23-000106",
    ]


def test_get_filing_by_accession(tmp_path: Path) -> None:
    reg = _registry(tmp_path)
    reg.build_company_from_artifacts([_sample_builder().primary_artifact()])
    record = reg.get_filing(CIK, "000032019323000106")  # undashed lookup
    assert record is not None
    assert record.form == "10-K"


def test_get_missing_filing_returns_none(tmp_path: Path) -> None:
    reg = _registry(tmp_path)
    reg.build_company_from_artifacts([_sample_builder().primary_artifact()])
    assert reg.get_filing(CIK, "0000320193-01-000001") is None


def test_filings_by_form_exact_match(tmp_path: Path) -> None:
    reg = _registry(tmp_path)
    b = _sample_builder().add(
        FilingRow(
            accession="0000320193-24-000001",
            form="10-K/A",
            report_date="2023-09-30",
            filing_date="2024-01-05",
            acceptance="2024-01-05T18:00:00.000Z",
        )
    )
    reg.build_company_from_artifacts([b.primary_artifact()])
    tens = reg.filings_by_form(CIK, "10-K")
    # 10-K/A must NOT be returned for form "10-K".
    assert [f.accession_number for f in tens] == ["0000320193-23-000106"]
    amendments = reg.filings_by_form(CIK, "10-K/A")
    assert [f.accession_number for f in amendments] == ["0000320193-24-000001"]


def test_list_company_ids(tmp_path: Path) -> None:
    reg = _registry(tmp_path)
    reg.build_company_from_artifacts([_sample_builder().primary_artifact()])
    assert reg.list_company_ids() == ["cik:0000320193"]


# -- pagination ---------------------------------------------------------------


def test_pagination_across_overflow_pages(tmp_path: Path) -> None:
    b = SubmissionsBuilder(CIK, overflow_files=["CIK0000320193-submissions-001.json"])
    b.add(FilingRow(accession="0000320193-23-000106", form="10-K"))
    overflow_rows = [
        FilingRow(accession="0000320193-10-000001", form="10-K"),
        FilingRow(accession="0000320193-11-000002", form="10-Q"),
    ]
    reg = _registry(tmp_path)
    reg.build_company_from_artifacts(
        [
            b.primary_artifact(),
            b.overflow_artifact("CIK0000320193-submissions-001.json", overflow_rows),
        ]
    )
    filings = reg.list_filings(CIK)
    assert len(filings) == 3
    assert {f.accession_number for f in filings} == {
        "0000320193-23-000106",
        "0000320193-10-000001",
        "0000320193-11-000002",
    }


def test_duplicate_accession_across_pages_deduped(tmp_path: Path) -> None:
    b = SubmissionsBuilder(CIK, overflow_files=["p1.json"])
    row = FilingRow(
        accession="0000320193-23-000106",
        form="10-K",
        filing_date="2023-11-03",
    )
    b.add(row)
    reg = _registry(tmp_path)
    result = reg.build_company_from_artifacts(
        [b.primary_artifact(), b.overflow_artifact("p1.json", [row])]
    )
    assert len(result) == 1


def test_inconsistent_duplicate_fails_closed(tmp_path: Path) -> None:
    b = SubmissionsBuilder(CIK, overflow_files=["p1.json"])
    b.add(
        FilingRow(
            accession="0000320193-23-000106", form="10-K", filing_date="2023-11-03"
        )
    )
    conflicting = FilingRow(
        accession="0000320193-23-000106", form="10-K", filing_date="2099-01-01"
    )
    reg = _registry(tmp_path)
    with pytest.raises(SourceValidationError, match="inconsistent duplicate"):
        reg.build_company_from_artifacts(
            [b.primary_artifact(), b.overflow_artifact("p1.json", [conflicting])]
        )


def test_empty_submissions_produces_empty_registry(tmp_path: Path) -> None:
    b = SubmissionsBuilder(CIK)
    reg = _registry(tmp_path)
    assert reg.build_company_from_artifacts([b.primary_artifact()]) == []
    assert reg.list_filings(CIK) == []


# -- determinism & rebuild ----------------------------------------------------


def test_build_is_order_independent(tmp_path: Path) -> None:
    b = SubmissionsBuilder(CIK, overflow_files=["p1.json"])
    b.add(FilingRow(accession="0000320193-23-000106", form="10-K"))
    overflow = [FilingRow(accession="0000320193-10-000001", form="10-K")]
    primary = b.primary_artifact()
    page = b.overflow_artifact("p1.json", overflow)

    reg1 = _registry(tmp_path / "a")
    r1 = reg1.build_company_from_artifacts([primary, page])
    reg2 = _registry(tmp_path / "b")
    r2 = reg2.build_company_from_artifacts([page, primary])  # reversed

    assert [x.to_dict() for x in r1] == [x.to_dict() for x in r2]


def test_rebuild_produces_identical_bytes(tmp_path: Path) -> None:
    b = _sample_builder()
    store = RegistryStore(tmp_path / "registry")
    reg = FilingRegistry(store)

    reg.build_company_from_artifacts([b.primary_artifact()])
    path = store._filing_path("cik:0000320193")
    first_bytes = path.read_bytes()

    # Delete derived state; rebuild from the same artifacts.
    path.unlink()
    assert not path.exists()
    reg.build_company_from_artifacts([b.primary_artifact()])
    assert path.read_bytes() == first_bytes


def test_no_wallclock_field_in_serialized_record(tmp_path: Path) -> None:
    reg = _registry(tmp_path)
    (record,) = reg.build_company_from_artifacts(
        [
            SubmissionsBuilder(CIK)
            .add(FilingRow(accession="0000320193-23-000106", form="10-K"))
            .primary_artifact()
        ]
    )
    serialized = record.to_dict()
    # Derivation timestamp is metadata, never part of logical identity.
    assert "derived_at" not in serialized
    assert "retrieved_at" not in serialized


def test_transformation_version_id_deterministic() -> None:
    assert (
        TransformationVersion().transformation_version_id
        == TransformationVersion().transformation_version_id
    )


def test_changing_logic_version_changes_id() -> None:
    a = TransformationVersion(code_version="filing-registry/1")
    b = TransformationVersion(code_version="filing-registry/2")
    assert a.transformation_version_id != b.transformation_version_id
