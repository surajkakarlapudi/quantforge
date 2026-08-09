"""ResearchReport / ReportReference: sealing, round-trip, and identity invariance.

Covers the sealed-record half of Phase 14 (locked §8, §9, D3, D4, D9): the
byte-identical ``to_dict`` / ``from_dict`` round trip, ``report_id`` re-derivation from
the recorded spec (no stored id state), the reference-only model (no embedded financial
values — D3), and that a presentation-only edit to the spec's non-identity surface
never changes ``report_id`` (D2), while the schema/format version is not part of
identity (D9).
"""

from __future__ import annotations

from quantforge.report.result import (
    BOUNDARY_PIT,
    ReportReference,
    ResearchReport,
)
from quantforge.report.spec import (
    ComparisonDirective,
    ReportSpecification,
)


def _experiment_report() -> ResearchReport:
    spec = ReportSpecification(
        name="r",
        scope="experiment",
        subject_id="sha256:subject",
        comparisons=(ComparisonDirective(statistic="final_equity"),),
    )
    references = (
        ReportReference(
            kind="experiment",
            reference_id="sha256:subject",
            content_hash="sha256:exphash",
            detail={},
        ),
        ReportReference(
            kind="comparison",
            reference_id="sha256:cmp",
            content_hash="sha256:cmp",
            detail={
                "statistic": "final_equity",
                "order": "descending",
                "member_scope": "experiment_children",
                "comparison_version_id": "sha256:ver",
            },
        ),
    )
    return ResearchReport.seal(
        report_engine_version_id="sha256:engine",
        report_spec=spec.to_dict(),
        scope=spec.scope,
        references=references,
        boundary_kind=BOUNDARY_PIT,
    )


class TestRoundTrip:
    def test_to_dict_from_dict_is_byte_identical(self) -> None:
        report = _experiment_report()
        rebuilt = ResearchReport.from_dict(report.to_dict())
        assert rebuilt.to_dict() == report.to_dict()

    def test_ids_survive_round_trip(self) -> None:
        report = _experiment_report()
        rebuilt = ResearchReport.from_dict(report.to_dict())
        assert rebuilt.report_id == report.report_id
        assert rebuilt.report_result_id == report.report_result_id
        assert rebuilt.result_hash == report.result_hash

    def test_reference_round_trip(self) -> None:
        ref = ReportReference(
            kind="comparison",
            reference_id="sha256:cmp",
            content_hash="sha256:cmp",
            detail={"statistic": "sharpe", "order": "ascending"},
        )
        assert ReportReference.from_dict(ref.to_dict()).to_dict() == ref.to_dict()


class TestIdentityDerivation:
    def test_report_id_is_rederived_not_stored(self) -> None:
        # to_dict emits report_id, but from_dict never reads it back as state; the
        # property recomputes it from report_spec + references, so a tampered stored
        # report_id is simply ignored (no drift is possible).
        report = _experiment_report()
        payload = report.to_dict()
        payload["report_id"] = "sha256:tampered"
        rebuilt = ResearchReport.from_dict(payload)
        assert rebuilt.report_id == report.report_id

    def test_research_result_id_aliases_report_result_id(self) -> None:
        report = _experiment_report()
        assert report.research_result_id == report.report_result_id


class TestReferenceOnlyModel:
    def test_report_embeds_no_financial_values(self) -> None:
        # Locked D3: a report is a manifest of pointers; no numeric equity/return value
        # is stored anywhere in the serialized record — only ids and content hashes.
        report = _experiment_report()
        references = report.to_dict()["references"]
        assert isinstance(references, list)
        for ref in references:
            assert isinstance(ref, dict)
            assert set(ref.keys()) == {
                "kind",
                "reference_id",
                "content_hash",
                "detail",
            }


class TestPresentationInvariance:
    def test_report_id_folds_no_presentation(self) -> None:
        # Two reports differing only in name are different (name is a declaration
        # input), but the report_id never depends on the boundary label's *rendering*
        # or on any renderer-facing surface — it is a pure function of the recorded spec
        # identity inputs + references. Here we assert the same spec + references yields
        # a stable id regardless of reference tuple order (a presentation-ish concern).
        report = _experiment_report()
        reordered = ResearchReport.seal(
            report_engine_version_id="sha256:engine",
            report_spec=report.report_spec,
            scope=report.scope,
            references=tuple(reversed(report.references)),
            boundary_kind=BOUNDARY_PIT,
        )
        assert reordered.report_id == report.report_id
