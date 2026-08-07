"""The filing-registry data model — derived records and their provenance.

These are the *derived* records the registry produces from immutable
acquisition artifacts. They follow ``docs/data-model.md`` (the **Filing**
entity, §4/§11, and amendment semantics §7.1) and hold only what the registry
is allowed to know: *facts about filings*, never interpreted financial content.

Design commitments encoded here:

* **Raw artifacts are authoritative; these records are derived.** Every
  :class:`FilingRecord` carries :class:`FilingProvenance` pointing back to the
  immutable source artifact (by SHA-256), so a record can always be traced to,
  and rebuilt from, the raw evidence. The registry never overwrites raw bytes.
* **Identity never depends on mutable or nondeterministic values.**
  ``filing_id``/``company_id`` derive only from the accession number and CIK
  (§11). A derivation timestamp, when recorded, is *metadata only* and is
  excluded from a record's logical identity / canonical serialization.
* **Absence is preserved, never fabricated.** Missing report date, acceptance
  timestamp, or primary-document description are ``None`` — we assert nothing.
* **Uncertainty is represented, not guessed.** Amendment linkage carries an
  explicit :class:`AmendmentLinkConfidence` (§7.1); an undefensible link is
  ``UNKNOWN`` with no fabricated base accession.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from quantforge.registry.identity import (
    canonical_accession,
)
from quantforge.registry.identity import (
    company_id as _company_id,
)
from quantforge.registry.identity import (
    filing_id as _filing_id,
)
from quantforge.sec.artifacts import ArtifactType

__all__ = [
    "AmendmentLinkConfidence",
    "DocumentReference",
    "FilingProvenance",
    "FilingRecord",
    "base_form",
    "is_amendment_form",
    "make_filing_record",
]


class AmendmentLinkConfidence(StrEnum):
    """How confidently an amendment's base filing was identified (§7.1).

    Terminology is taken verbatim from ``docs/data-model.md`` §7.1 / invariant
    22a. SEC exposes no explicit base-accession field anywhere in structured
    metadata, so any link is *derived*; this enum records how defensible that
    derivation is. ``UNKNOWN`` means no base could be defensibly identified —
    we represent the amendment standalone rather than guess.
    """

    #: SEC (or the filing itself) states the base accession explicitly.
    #: Reserved; not observed in structured metadata for periodic reports.
    SOURCE_ASSERTED = "SOURCE_ASSERTED"
    #: Form is exactly ``base + "/A"``, same CIK, same report date, exactly one
    #: candidate base filing, consistent chronology (amendment after base).
    DERIVED_HIGH_CONFIDENCE = "DERIVED_HIGH_CONFIDENCE"
    #: ``/A`` + same period but the base is ambiguous (several candidates) or
    #: chronology matched only approximately.
    DERIVED_LOW_CONFIDENCE = "DERIVED_LOW_CONFIDENCE"
    #: No defensible base identifiable. The amendment stands alone.
    UNKNOWN = "UNKNOWN"


def is_amendment_form(form: str) -> bool:
    """True if ``form`` is an amendment (SEC marks these with a ``/A`` suffix).

    This is a property of the form label as SEC supplies it — e.g. ``10-K/A``,
    ``10-Q/A``, ``8-K/A``. It says the filing *is* an amendment; it says nothing
    about *which* filing it amends (that is derived separately, §7.1).
    """
    return form.strip().upper().endswith("/A")


def base_form(form: str) -> str:
    """Return the base form of an amendment, e.g. ``10-K/A`` → ``10-K``.

    For a non-amendment form the input is returned unchanged. Purely a string
    operation on the SEC-supplied label; no interpretation of contents.
    """
    stripped = form.strip()
    if stripped.upper().endswith("/A"):
        return stripped[:-2]
    return stripped


@dataclass(frozen=True, slots=True)
class DocumentReference:
    """A reference from a filing to one acquired artifact in its package.

    Records only *that this artifact belongs to this filing* plus the immutable
    content address — never any parsed content. ``artifact_type`` is the Phase 1
    classification captured at acquisition time; ``is_primary_document`` marks
    the artifact whose filename matches the filing's ``primary_document``.
    """

    artifact_sha256: str
    artifact_type: ArtifactType
    source_url: str
    is_primary_document: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "artifact_sha256": self.artifact_sha256,
            "artifact_type": self.artifact_type.value,
            "source_url": self.source_url,
            "is_primary_document": self.is_primary_document,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> DocumentReference:
        return cls(
            artifact_sha256=_req_str(raw, "artifact_sha256"),
            artifact_type=ArtifactType(_req_str(raw, "artifact_type")),
            source_url=_req_str(raw, "source_url"),
            is_primary_document=bool(raw.get("is_primary_document", False)),
        )


@dataclass(frozen=True, slots=True)
class FilingProvenance:
    """The immutable evidence a :class:`FilingRecord` was derived from.

    Every record traces back to the exact acquisition artifact (by content
    hash) it was parsed out of, the endpoint that produced it, and the registry
    logic version that performed the derivation. ``derived_at`` is descriptive
    metadata only (data-model §9) and is **not** part of logical identity: it is
    excluded from :meth:`FilingRecord.to_dict`, so a rebuild reproduces
    byte-identical logical records regardless of when it runs.
    """

    source_artifact_sha256: str
    source_artifact_type: ArtifactType
    source_url: str
    transformation_version_id: str

    def to_dict(self) -> dict[str, object]:
        return {
            "source_artifact_sha256": self.source_artifact_sha256,
            "source_artifact_type": self.source_artifact_type.value,
            "source_url": self.source_url,
            "transformation_version_id": self.transformation_version_id,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> FilingProvenance:
        return cls(
            source_artifact_sha256=_req_str(raw, "source_artifact_sha256"),
            source_artifact_type=ArtifactType(_req_str(raw, "source_artifact_type")),
            source_url=_req_str(raw, "source_url"),
            transformation_version_id=_req_str(raw, "transformation_version_id"),
        )


@dataclass(frozen=True, slots=True)
class FilingRecord:
    """One SEC filing, as known to the registry (metadata + provenance only).

    Attributes
    ----------
    filing_id / company_id:
        Canonical identities (§11), derived only from accession and CIK.
    accession_number:
        Canonical dashed accession (the ``filing_id`` payload).
    accession_number_original:
        The accession string exactly as SEC supplied it, preserved for
        provenance/audit even though identity uses the canonical form.
    form:
        The SEC form label as supplied (``10-K``, ``10-K/A``, ``8-K``, ...).
    filing_date / report_date:
        Distinct dates, never collapsed. ``filing_date`` is the legal
        "filed as of" date; ``report_date`` is the period of report. Neither is
        public-availability. ``report_date`` is ``None`` when SEC omits it
        (e.g. non-periodic forms).
    acceptance_timestamp_utc:
        EDGAR ``acceptanceDateTime``, stored **exactly as supplied (UTC)** — no
        timezone conversion here (data-model §6.4). ``None`` when absent.
        Acceptance is *not* public availability.
    primary_document / primary_document_description:
        The package's primary document filename and its SEC description, when
        supplied; ``None`` otherwise.
    is_amendment:
        Whether ``form`` carries a ``/A`` suffix (source metadata).
    amends_accession:
        Canonical accession of the amended base filing when defensibly derived;
        ``None`` otherwise (including for non-amendments and ``UNKNOWN`` links).
    amendment_link_confidence:
        Confidence of ``amends_accession`` (§7.1); ``None`` for non-amendments.
    documents:
        References to acquired artifacts belonging to this filing.
    provenance:
        The immutable source artifact this record was derived from.
    """

    filing_id: str
    company_id: str
    accession_number: str
    accession_number_original: str
    form: str
    filing_date: str | None
    report_date: str | None
    acceptance_timestamp_utc: str | None
    primary_document: str | None
    primary_document_description: str | None
    is_amendment: bool
    amends_accession: str | None
    amendment_link_confidence: AmendmentLinkConfidence | None
    provenance: FilingProvenance
    documents: tuple[DocumentReference, ...] = ()

    def with_documents(self, documents: tuple[DocumentReference, ...]) -> FilingRecord:
        """Return a copy with ``documents`` replaced (records are immutable)."""
        return FilingRecord(
            filing_id=self.filing_id,
            company_id=self.company_id,
            accession_number=self.accession_number,
            accession_number_original=self.accession_number_original,
            form=self.form,
            filing_date=self.filing_date,
            report_date=self.report_date,
            acceptance_timestamp_utc=self.acceptance_timestamp_utc,
            primary_document=self.primary_document,
            primary_document_description=self.primary_document_description,
            is_amendment=self.is_amendment,
            amends_accession=self.amends_accession,
            amendment_link_confidence=self.amendment_link_confidence,
            provenance=self.provenance,
            documents=documents,
        )

    def with_amendment(
        self,
        amends_accession: str | None,
        confidence: AmendmentLinkConfidence | None,
    ) -> FilingRecord:
        """Return a copy with amendment linkage replaced (records are immutable)."""
        return FilingRecord(
            filing_id=self.filing_id,
            company_id=self.company_id,
            accession_number=self.accession_number,
            accession_number_original=self.accession_number_original,
            form=self.form,
            filing_date=self.filing_date,
            report_date=self.report_date,
            acceptance_timestamp_utc=self.acceptance_timestamp_utc,
            primary_document=self.primary_document,
            primary_document_description=self.primary_document_description,
            is_amendment=self.is_amendment,
            amends_accession=amends_accession,
            amendment_link_confidence=confidence,
            provenance=self.provenance,
            documents=self.documents,
        )

    def to_dict(self) -> dict[str, object]:
        """Serialize to the record's **logical identity** (deterministic).

        No wall-clock, ordering-dependent, or otherwise nondeterministic field
        appears here — documents are emitted in a stable sorted order — so two
        rebuilds from the same artifacts under the same logic version produce
        byte-identical output.
        """
        confidence = self.amendment_link_confidence
        return {
            "filing_id": self.filing_id,
            "company_id": self.company_id,
            "accession_number": self.accession_number,
            "accession_number_original": self.accession_number_original,
            "form": self.form,
            "filing_date": self.filing_date,
            "report_date": self.report_date,
            "acceptance_timestamp_utc": self.acceptance_timestamp_utc,
            "primary_document": self.primary_document,
            "primary_document_description": self.primary_document_description,
            "is_amendment": self.is_amendment,
            "amends_accession": self.amends_accession,
            "amendment_link_confidence": (
                confidence.value if confidence is not None else None
            ),
            "documents": [
                doc.to_dict()
                for doc in sorted(
                    self.documents,
                    key=lambda d: (d.artifact_type.value, d.artifact_sha256),
                )
            ],
            "provenance": self.provenance.to_dict(),
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> FilingRecord:
        raw_conf = raw.get("amendment_link_confidence")
        confidence = (
            AmendmentLinkConfidence(raw_conf) if isinstance(raw_conf, str) else None
        )
        raw_docs = raw.get("documents", [])
        documents = tuple(
            DocumentReference.from_dict(d)
            for d in (raw_docs if isinstance(raw_docs, list) else [])
            if isinstance(d, dict)
        )
        provenance_raw = raw["provenance"]
        if not isinstance(provenance_raw, dict):
            raise ValueError("provenance must be an object")
        return cls(
            filing_id=_req_str(raw, "filing_id"),
            company_id=_req_str(raw, "company_id"),
            accession_number=_req_str(raw, "accession_number"),
            accession_number_original=_req_str(raw, "accession_number_original"),
            form=_req_str(raw, "form"),
            filing_date=_opt_str(raw, "filing_date"),
            report_date=_opt_str(raw, "report_date"),
            acceptance_timestamp_utc=_opt_str(raw, "acceptance_timestamp_utc"),
            primary_document=_opt_str(raw, "primary_document"),
            primary_document_description=_opt_str(raw, "primary_document_description"),
            is_amendment=bool(raw.get("is_amendment", False)),
            amends_accession=_opt_str(raw, "amends_accession"),
            amendment_link_confidence=confidence,
            provenance=FilingProvenance.from_dict(provenance_raw),
            documents=documents,
        )


def make_filing_record(
    *,
    cik: str | int,
    accession_original: str,
    form: str,
    filing_date: str | None,
    report_date: str | None,
    acceptance_timestamp_utc: str | None,
    primary_document: str | None,
    primary_document_description: str | None,
    provenance: FilingProvenance,
) -> FilingRecord:
    """Construct a :class:`FilingRecord`, canonicalizing identity fields.

    Amendment linkage is left un-derived here (``amends_accession=None``,
    confidence ``UNKNOWN`` for amendments / ``None`` for non-amendments); it is
    filled in by the amendment-inference pass, which needs the whole cohort.
    """
    canonical = canonical_accession(accession_original)
    amendment = is_amendment_form(form)
    return FilingRecord(
        filing_id=_filing_id(canonical),
        company_id=_company_id(cik),
        accession_number=canonical,
        accession_number_original=accession_original,
        form=form,
        filing_date=filing_date,
        report_date=report_date,
        acceptance_timestamp_utc=acceptance_timestamp_utc,
        primary_document=primary_document,
        primary_document_description=primary_document_description,
        is_amendment=amendment,
        amends_accession=None,
        amendment_link_confidence=(
            AmendmentLinkConfidence.UNKNOWN if amendment else None
        ),
        provenance=provenance,
    )


def _req_str(raw: dict[str, object], key: str) -> str:
    value = raw[key]
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string")
    return value


def _opt_str(raw: dict[str, object], key: str) -> str | None:
    value = raw.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string or null")
    return value
