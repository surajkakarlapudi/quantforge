"""The sealed, content-addressed research report & its reference manifest (locked §8).

A completed report is a :class:`ResearchReport`: the report identity, the engine
version,
the full :class:`~quantforge.report.spec.ReportSpecification` request
(for reproduction),
the top-level scope, the explicit PIT boundary, and the ordered
:class:`ReportReference` manifest — one entry per referenced sealed artifact, each
naming
the artifact by ``(kind, reference_id, content_hash)`` plus (for a comparison) the
reporting-intent ``detail``. Like every research record in this project it satisfies the
:class:`~quantforge.factors.store.ResearchRecord` Protocol (``research_result_id``
aliases
the report result id; deterministic ``to_dict``), so it persists write-once to the
shared
sidecar with **no new store** (locked D1).

The manifest deliberately stores only the *pointer* to each referenced artifact — its id
and content hash — never a copy of the artifact's body/ledger (locked D3). Each
referenced
record already lives in the same sidecar (a backtest / experiment the engine sealed
there),
so the report stays a thin, reproducible index over already-sealed, PIT-correct research
(locked §1, §11). ``result_hash`` seals the ordered reference digests, so the report id
pins both the request and every artifact it reports on: a single drifted artifact
changes
the whole report identity, honestly (locked §9).

Every value is deterministically serializable and round-trips byte-identically through
its
own ``from_dict`` (fail-closed decode, mirroring :mod:`quantforge.experiment.result`);
no
wall-clock, RNG, or iteration-order dependence enters any value or id. The report
carries
**no** numeric field of its own — it only references (locked §8).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from quantforge.report.identity import (
    report_id as _report_id,
)
from quantforge.report.identity import (
    report_reference_digest as _reference_digest,
)
from quantforge.report.identity import (
    report_result_hash as _result_hash,
)
from quantforge.report.identity import (
    report_result_id as _report_result_id,
)

__all__ = [
    "BOUNDARY_PIT",
    "REPORT_RESULT_FORMAT_VERSION",
    "ReportReference",
    "ResearchReport",
]

#: The §9/§14 record-schema version for the report record — distinct from the engine
#: logic version (``report_engine_version_id``) and from the sidecar's container format
#: version. Bump it when the serialized meaning of a report record changes. Per locked
#: D9 it is **not** folded into ``report_id`` (a container/format concern, not research
#: content); a bump is a future migration event, not an identity fork.
REPORT_RESULT_FORMAT_VERSION = "report-result/1"

#: The v1 point-in-time boundary label (locked §12, D10). Backtests/experiments are
#: PIT-only by construction, so a v1 report is always ``pit``; the report records this
#: explicitly (no default at the identity/decode layer) and the renderer must display
#: it.
#: A future REVISED-scope report is a distinct, explicitly-labeled boundary.
BOUNDARY_PIT = "pit"

#: The closed v1 reference-kind vocabulary. A record reference (``backtest`` /
#: ``experiment``) carries an empty ``detail``; a ``comparison`` reference carries the
#: reporting-intent detail and is recomputed at build/render (locked D5, D7).
_KIND_BACKTEST = "backtest"
_KIND_EXPERIMENT = "experiment"
_KIND_COMPARISON = "comparison"


def _req_str(raw: dict[str, object], key: str) -> str:
    """Read a required string from a decoded payload; fail closed otherwise."""
    value = raw[key]
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string")
    return value


def _req_list(raw: dict[str, object], key: str) -> list[object]:
    value = raw[key]
    if not isinstance(value, list):
        raise ValueError(f"{key} must be a list")
    return value


def _req_dict(raw: dict[str, object], key: str) -> dict[str, object]:
    value = raw[key]
    if not isinstance(value, dict):
        raise ValueError(f"{key} must be an object")
    return value


def _as_dict(value: object, key: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"each {key} entry must be an object")
    return value


@dataclass(frozen=True, slots=True)
class ReportReference:
    """One content-addressed pointer to a sealed artifact the report is about (§8.1).

    ``kind`` is the closed v1 reference vocabulary member (``backtest`` / ``experiment``
    / ``comparison``). ``reference_id`` is the ``backtest_id`` /
    ``experiment_result_id``
    / ``comparison_id``. ``content_hash`` is the thing that changes iff the referenced
    content changes: a record's ``result_hash``, or a comparison's self-addressing
    ``comparison_id`` (which already folds ``comparison_version_id`` + statistic + order
    + members). ``detail`` is the reporting intent — empty for a record reference; for a
    ``comparison`` it records exactly the inputs a reader needs to *recompute* the
    comparison deterministically (``statistic``, ``order``, ``member_scope``,
    ``comparison_version_id`` — locked D5), never a copy of the ranking itself.
    """

    kind: str
    reference_id: str
    content_hash: str
    detail: dict[str, object] = field(default_factory=dict)

    def digest(self) -> dict[str, object]:
        """The ``(kind, reference_id, content_hash, detail)`` fingerprint sealed into
        ``result_hash`` (locked §9).

        Because ``content_hash`` is the referenced record's ``result_hash`` (or a
        comparison's ``comparison_id``), sealing the digest is equivalent to sealing the
        referenced content — the report identity is sensitive to any artifact that
        changes.
        """
        return _reference_digest(
            kind=self.kind,
            reference_id=self.reference_id,
            content_hash=self.content_hash,
            detail=self.detail,
        )

    def descriptor(self) -> list[str]:
        """The ``[kind, reference_id]`` pair folded (sorted, as a set) into
        ``report_id``."""
        return [self.kind, self.reference_id]

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "reference_id": self.reference_id,
            "content_hash": self.content_hash,
            "detail": dict(self.detail),
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> ReportReference:
        """Reconstruct from a :meth:`to_dict` payload; ``detail`` copied verbatim.

        The additive inverse of :meth:`to_dict`, so a re-emitted :meth:`to_dict` is
        byte-identical and the sealed reference digest is unchanged.
        """
        return cls(
            kind=_req_str(raw, "kind"),
            reference_id=_req_str(raw, "reference_id"),
            content_hash=_req_str(raw, "content_hash"),
            detail=dict(_req_dict(raw, "detail")),
        )


@dataclass(frozen=True, slots=True)
class ResearchReport:
    """A complete, sealed, content-addressed research report (locked §8.2, §9, D1).

    Implements the :class:`~quantforge.factors.store.ResearchRecord` Protocol
    (:attr:`research_result_id` aliases :attr:`report_result_id`; deterministic
    :meth:`to_dict`), so it persists write-once to the shared research sidecar with no
    new store. It records the engine version, the exact
    :class:`~quantforge.report.spec.ReportSpecification` request (``report_spec`` — for
    reproduction), the top-level ``scope``, the ordered :class:`ReportReference`
    manifest,
    the explicit ``boundary_kind`` (locked D10), and the sealed ``result_hash`` over the
    ordered reference digests. It holds **no** presentation and **no** numeric field of
    its own (locked §8, §10) — those are the renderer's concern.
    """

    report_engine_version_id: str
    report_spec: dict[str, object]
    scope: str
    references: tuple[ReportReference, ...]
    boundary_kind: str
    result_hash: str

    @property
    def report_id(self) -> str:
        """The content-addressed request id (``sha256:``) — declaration +
        referenced set.

        Re-derived (never stored as state) from the recorded ``report_spec`` and the
        ordered references, so ``from_dict(to_dict(r))`` reproduces it exactly. Folds
        the
        name, spec version, scope, subject id, the sorted ``(kind, id)`` reference
        descriptors, and the sorted comparison directives (locked §9).
        """
        return _report_id(
            name=_req_str(self.report_spec, "name"),
            spec_version=_req_str(self.report_spec, "spec_version"),
            scope=self.scope,
            subject_id=_req_str(self.report_spec, "subject_id"),
            sorted_reference_descriptors=sorted(
                (ref.descriptor() for ref in self.references),
                key=lambda pair: (pair[0], pair[1]),
            ),
            comparison_directives=self._comparison_descriptors(),
        )

    @property
    def report_result_id(self) -> str:
        """The content-addressed sidecar key: ``sha256`` of id+engine+result_hash
        (§9)."""
        return _report_result_id(
            report_id=self.report_id,
            report_engine_version_id=self.report_engine_version_id,
            result_hash=self.result_hash,
        )

    @property
    def research_result_id(self) -> str:
        """Alias of :attr:`report_result_id` — the ``ResearchRecord`` identity
        (§8.2)."""
        return self.report_result_id

    def _comparison_descriptors(self) -> list[list[str]]:
        """The sorted ``(statistic, order)`` directives from the recorded spec (§9)."""
        raw = self.report_spec.get("comparisons", [])
        if not isinstance(raw, list):
            raise ValueError("report_spec.comparisons must be a list")
        descriptors: list[list[str]] = []
        for entry in raw:
            if not isinstance(entry, dict):
                raise ValueError("each report_spec.comparisons entry must be an object")
            descriptors.append([_req_str(entry, "statistic"), _req_str(entry, "order")])
        return sorted(descriptors, key=lambda pair: (pair[0], pair[1]))

    @classmethod
    def seal(
        cls,
        *,
        report_engine_version_id: str,
        report_spec: dict[str, object],
        scope: str,
        references: tuple[ReportReference, ...],
        boundary_kind: str,
    ) -> ResearchReport:
        """Seal a resolved reference manifest, computing ``result_hash`` (locked §9).

        The single constructor the engine uses: it folds the ordered reference digests
        into ``result_hash``, so identity is a pure function of the reporting request
        and
        the referenced content and never has to be supplied by the caller.
        """
        rhash = _result_hash([ref.digest() for ref in references])
        return cls(
            report_engine_version_id=report_engine_version_id,
            report_spec=dict(report_spec),
            scope=scope,
            references=references,
            boundary_kind=boundary_kind,
            result_hash=rhash,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "report_result_id": self.report_result_id,
            # The ResearchRecord alias so the generic sidecar reader keys correctly.
            "research_result_id": self.research_result_id,
            "report_id": self.report_id,
            "report_engine_version_id": self.report_engine_version_id,
            "report_spec": dict(self.report_spec),
            "scope": self.scope,
            "references": [ref.to_dict() for ref in self.references],
            "boundary_kind": self.boundary_kind,
            "result_hash": self.result_hash,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> ResearchReport:
        """Reconstruct a sealed report from its :meth:`to_dict` payload (locked §8.2).

        The additive inverse of :meth:`to_dict`, so a report read back from the shared
        sidecar via ``store.read_as(id, ResearchReport.from_dict)`` is a first-class
        typed object. ``report_id`` / ``report_result_id`` / ``research_result_id`` are
        derived aliases re-emitted by their properties (not stored as state), and the
        reference manifest round-trips in stored order — so ``from_dict(to_dict(r))``
        re-emits an identical ``to_dict`` and the same ``result_hash``, no drift.
        """
        return cls(
            report_engine_version_id=_req_str(raw, "report_engine_version_id"),
            report_spec=dict(_req_dict(raw, "report_spec")),
            scope=_req_str(raw, "scope"),
            references=tuple(
                ReportReference.from_dict(_as_dict(item, "references"))
                for item in _req_list(raw, "references")
            ),
            boundary_kind=_req_str(raw, "boundary_kind"),
            result_hash=_req_str(raw, "result_hash"),
        )
