"""Deterministic dimensions_hash canonicalization (§15.5)."""

from __future__ import annotations

from quantforge.xbrl.dimensions import (
    EMPTY_DIMENSIONS_SENTINEL,
    RawDimension,
    canonical_dimensions_key,
    dimensions_hash,
    normalize_typed_text,
)
from quantforge.xbrl.qnames import QName


def _axis(local: str) -> QName:
    return QName("http://fasb.org/us-gaap/2023", local)


def _member(local: str) -> QName:
    return QName("http://fasb.org/us-gaap/2023", local)


def test_empty_dimensions_use_sentinel() -> None:
    assert canonical_dimensions_key(()) == EMPTY_DIMENSIONS_SENTINEL
    # Every context, even undimensioned, has a stable hash.
    assert dimensions_hash(()).startswith("sha256:")


def test_dimension_order_does_not_affect_hash() -> None:
    a = RawDimension.explicit(_axis("AxisA"), _member("MemberA"))
    b = RawDimension.explicit(_axis("AxisB"), _member("MemberB"))
    assert dimensions_hash((a, b)) == dimensions_hash((b, a))


def test_different_members_produce_different_hash() -> None:
    a = RawDimension.explicit(_axis("Axis"), _member("MemberA"))
    b = RawDimension.explicit(_axis("Axis"), _member("MemberB"))
    assert dimensions_hash((a,)) != dimensions_hash((b,))


def test_typed_member_hash_includes_child_and_text() -> None:
    t1 = RawDimension.typed(_axis("Axis"), _member("Child"), "row-1")
    t2 = RawDimension.typed(_axis("Axis"), _member("Child"), "row-2")
    assert dimensions_hash((t1,)) != dimensions_hash((t2,))


def test_typed_text_whitespace_normalized() -> None:
    assert normalize_typed_text("  a   b ") == "a b"
    assert normalize_typed_text(None) == ""
    t1 = RawDimension.typed(_axis("Axis"), _member("Child"), " row 1 ")
    t2 = RawDimension.typed(_axis("Axis"), _member("Child"), "row 1")
    assert dimensions_hash((t1,)) == dimensions_hash((t2,))


def test_explicit_and_typed_on_same_axis_differ() -> None:
    e = RawDimension.explicit(_axis("Axis"), _member("Member"))
    t = RawDimension.typed(_axis("Axis"), _member("Member"), "Member")
    assert dimensions_hash((e,)) != dimensions_hash((t,))
