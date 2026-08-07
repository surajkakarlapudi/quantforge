"""Tests for versioned policies & reproducible snapshot manifests (§9, §PA.2).

Pins content-addressed identity determinism (invariants 14, 19, 20): a policy id
is a pure function of ``(policy_id, policy_version, rule_definition_hash)``, a rule
change forces a new id, and a :class:`DatasetVersion` Merkle root is
order-independent over its members but sensitive to any content change.
"""

from __future__ import annotations

import dataclasses

from quantforge.availability.version import (
    AvailabilityRule,
    DatasetVersion,
    PolicyConfidence,
    PolicyStatus,
    edgar_std_v1,
    merkle_root,
)


class TestPolicyIdentity:
    def test_id_is_deterministic(self) -> None:
        assert edgar_std_v1().availability_policy_id == (
            edgar_std_v1().availability_policy_id
        )

    def test_rule_change_changes_id(self) -> None:
        base = edgar_std_v1()
        changed = dataclasses.replace(
            base,
            rule_definition=AvailabilityRule(cutoff_local_time="16:00"),
        )
        assert base.availability_policy_id != changed.availability_policy_id

    def test_version_bump_changes_id(self) -> None:
        base = edgar_std_v1()
        v2 = dataclasses.replace(base, policy_version="v2")
        assert base.availability_policy_id != v2.availability_policy_id

    def test_id_is_sha256_prefixed(self) -> None:
        assert edgar_std_v1().availability_policy_id.startswith("sha256:")

    def test_roundtrip_preserves_id(self) -> None:
        base = edgar_std_v1()
        restored = type(base).from_dict(base.to_dict())
        assert restored.availability_policy_id == base.availability_policy_id
        assert restored == base


class TestEdgarStdV1Mandate:
    def test_provisional_and_unvalidated(self) -> None:
        p = edgar_std_v1()
        assert p.status is PolicyStatus.PROVISIONAL
        assert p.confidence is PolicyConfidence.UNVALIDATED

    def test_never_trusts_dissemination(self) -> None:
        # Decision 4: the initial policy cannot reach verified.
        assert edgar_std_v1().rule_definition.dissemination_evidence_trusted is False

    def test_fails_closed_on_missing_acceptance(self) -> None:
        assert edgar_std_v1().rule_definition.fail_closed_on_missing_acceptance is True

    def test_wildcard_form_scope(self) -> None:
        p = edgar_std_v1()
        assert p.covers_form("10-K")
        assert p.covers_form("8-K")

    def test_era_bounded_after_dst_regime(self) -> None:
        # effective_from must be within the post-2007 DST regime the calendar
        # assumes, so the self-contained ET conversion is exactly correct.
        assert edgar_std_v1().effective_from >= "2007-01-01T00:00:00Z"


class TestMerkleRoot:
    def test_empty_is_fixed(self) -> None:
        assert merkle_root([]).startswith("sha256:")
        assert merkle_root([]) == merkle_root([])

    def test_order_sensitive_when_unsorted(self) -> None:
        # merkle_root itself is order-sensitive (the caller sorts first).
        assert merkle_root(["a", "b"]) != merkle_root(["b", "a"])

    def test_single_leaf_stable(self) -> None:
        assert merkle_root(["x"]) == merkle_root(["x"])

    def test_odd_leaf_count(self) -> None:
        # Three leaves exercises the odd-tail promotion path deterministically.
        assert merkle_root(["a", "b", "c"]) == merkle_root(["a", "b", "c"])


class TestDatasetVersion:
    def _dv(
        self,
        *,
        transformation_version_id: str = "sha256:tv",
        availability_policy_ids: tuple[str, ...] = ("sha256:p1",),
        raw_document_ids: tuple[str, ...] = ("sha256:d1", "sha256:d2"),
        fact_ids: tuple[str, ...] = ("f1", "f2"),
    ) -> DatasetVersion:
        return DatasetVersion(
            transformation_version_id=transformation_version_id,
            availability_policy_ids=availability_policy_ids,
            raw_document_ids=raw_document_ids,
            fact_ids=fact_ids,
        )

    def test_id_order_independent(self) -> None:
        # Member ordering does not change the id (members are sorted internally).
        a = self._dv(fact_ids=("f1", "f2"), raw_document_ids=("sha256:d1", "sha256:d2"))
        b = self._dv(fact_ids=("f2", "f1"), raw_document_ids=("sha256:d2", "sha256:d1"))
        assert a.dataset_version_id == b.dataset_version_id

    def test_id_changes_with_added_fact(self) -> None:
        a = self._dv()
        b = self._dv(fact_ids=("f1", "f2", "f3"))
        assert a.dataset_version_id != b.dataset_version_id

    def test_id_changes_with_policy_set(self) -> None:
        a = self._dv()
        b = self._dv(availability_policy_ids=("sha256:p1", "sha256:p2"))
        assert a.dataset_version_id != b.dataset_version_id

    def test_id_changes_with_transformation_version(self) -> None:
        a = self._dv()
        b = self._dv(transformation_version_id="sha256:tv2")
        assert a.dataset_version_id != b.dataset_version_id

    def test_roundtrip(self) -> None:
        dv = self._dv()
        restored = DatasetVersion.from_dict(dv.to_dict())
        assert restored.dataset_version_id == dv.dataset_version_id
