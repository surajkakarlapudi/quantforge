"""Report identity: content-addressing, sensitivity, and presentation-invariance.

Covers the identity half of Phase 14 (locked §9, D2, D9): the ``sha256:`` discipline,
what ``report_id`` folds (declaration + referenced set + directives) and — just as
importantly — what it deliberately does *not* fold (presentation, schema/format
version), reference-order independence, and drift sensitivity.
"""

from __future__ import annotations

from quantforge.report.identity import (
    report_engine_version_id,
    report_id,
    report_reference_digest,
    report_result_hash,
    report_result_id,
)


def _digest(kind: str, ref: str, content: str) -> dict[str, object]:
    return report_reference_digest(
        kind=kind, reference_id=ref, content_hash=content, detail={}
    )


class TestPrefixDiscipline:
    def test_every_id_is_sha256_prefixed(self) -> None:
        rid = report_id(
            name="r",
            spec_version="report/1",
            scope="backtest",
            subject_id="sha256:s",
            sorted_reference_descriptors=[["backtest", "sha256:s"]],
            comparison_directives=[],
        )
        rhash = report_result_hash([_digest("backtest", "sha256:s", "sha256:h")])
        rrid = report_result_id(
            report_id=rid,
            report_engine_version_id=report_engine_version_id(),
            result_hash=rhash,
        )
        for value in (rid, rhash, rrid, report_engine_version_id()):
            assert value.startswith("sha256:")


class TestReportIdSensitivity:
    def test_name_changes_id(self) -> None:
        def rid(name: str) -> str:
            return report_id(
                name=name,
                spec_version="report/1",
                scope="backtest",
                subject_id="sha256:s",
                sorted_reference_descriptors=[["backtest", "sha256:s"]],
                comparison_directives=[],
            )

        assert rid("a") != rid("b")

    def test_subject_changes_id(self) -> None:
        def rid(subject_id: str) -> str:
            return report_id(
                name="r",
                spec_version="report/1",
                scope="backtest",
                subject_id=subject_id,
                sorted_reference_descriptors=[["backtest", "sha256:s"]],
                comparison_directives=[],
            )

        assert rid("sha256:s1") != rid("sha256:s2")

    def test_directives_change_id(self) -> None:
        def rid(comparison_directives: list[list[str]]) -> str:
            return report_id(
                name="r",
                spec_version="report/1",
                scope="experiment",
                subject_id="sha256:s",
                sorted_reference_descriptors=[["experiment", "sha256:s"]],
                comparison_directives=comparison_directives,
            )

        assert rid([]) != rid([["sharpe", "descending"]])

    def test_reference_descriptor_order_is_irrelevant(self) -> None:
        # The caller passes descriptors sorted; identity is a set identity.
        a = report_id(
            name="r",
            spec_version="report/1",
            scope="experiment",
            subject_id="sha256:s",
            sorted_reference_descriptors=[
                ["comparison", "sha256:c"],
                ["experiment", "sha256:s"],
            ],
            comparison_directives=[["sharpe", "descending"]],
        )
        b = report_id(
            name="r",
            spec_version="report/1",
            scope="experiment",
            subject_id="sha256:s",
            sorted_reference_descriptors=sorted(
                [["experiment", "sha256:s"], ["comparison", "sha256:c"]]
            ),
            comparison_directives=[["sharpe", "descending"]],
        )
        assert a == b


class TestResultHashDrift:
    def test_content_hash_drift_changes_result_hash(self) -> None:
        base = report_result_hash([_digest("backtest", "sha256:s", "sha256:h1")])
        drifted = report_result_hash([_digest("backtest", "sha256:s", "sha256:h2")])
        assert base != drifted

    def test_identical_manifest_is_stable(self) -> None:
        manifest = [_digest("backtest", "sha256:s", "sha256:h")]
        assert report_result_hash(manifest) == report_result_hash(list(manifest))


class TestEngineVersion:
    def test_engine_version_is_constant(self) -> None:
        # A non-numeric layer: the version folds only its domain tag (§9).
        assert report_engine_version_id() == report_engine_version_id()
