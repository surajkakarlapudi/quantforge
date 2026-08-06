"""The canonicalizer: RawFacts ⇒ canonical Facts (requirement 1, 19).

:class:`Canonicalizer` is the small, pure core of Phase 4. Given a Phase 3
:class:`~openfinance.xbrl.parser.ParsedInstance` (or its constituent raw records)
it produces the deterministic set of canonical
:class:`~openfinance.canonical.model.Fact` records, retaining complete lineage
back to every raw fact.

The transformation, per raw fact:

1. resolve its context (period + dimensional segment) and unit (structural
   measures) from the parsed instance — never guessed;
2. classify the concept + taxonomy (no concept mapping — requirement 2);
3. canonicalize the period (instant/duration/forever; no fiscal inference —
   requirement 4);
4. canonicalize the unit conservatively (UNKNOWN when unsure — requirement 6);
5. fold scale & sign into an exact-``Decimal`` base-unit value, preserving nil ≠
   zero and the raw lexical value/scale/sign/decimals (requirements 7, 8);
6. compute the deterministic ``obs_key`` and ``fact_id`` (§6.2, §11).

**Cardinality (data-model §4).** One or more raw facts that reduce to the same
``obs_key`` within one filing collapse to *at most one* Fact (they share a
``fact_id``). A genuine duplicate (identical canonical value) collapses silently
to one Fact whose provenance lists every contributing raw fact, with the
lowest-ordinal raw fact as the canonical representative.

**Same-obs_key precision variants (data-model open-question 8).** Real SEC
filings routinely report the *same economic value* twice within one filing at
different ``decimals`` precision — e.g. Apple's ``UnrecognizedTaxBenefits`` as
23,242,000,000 (``decimals=-6``) and 23,200,000,000 (``decimals=-8``), where the
second is exactly the first rounded to the nearest 10^8. Per the resolved policy
(**prefer most-precise ``decimals``**), such a group collapses to one Fact
carrying the *most-precise* value as the canonical representative, provided every
other member is a consistent rounding of it (within half its rounding unit). All
contributing raw facts are retained in provenance. A group whose values are **not**
reconcilable this way — a genuine value contradiction, a nil-vs-number mismatch,
or a member whose precision cannot be read — is a source data-quality defect we
must not arbitrate: we fail closed with
:class:`~openfinance.canonical.errors.CanonicalContradictionError` (§13 case 8).

**No silent drops (requirement 16).** Every raw fact either contributes to a Fact
or triggers an explicit error. The canonicalizer never discards a fact.

**Determinism (requirement 14, invariant 18).** Output is a pure function of the
raw records + transformation version: identity uses no wall-clock/RNG/order;
duplicate grouping is resolved by a deterministic representative; facts are
returned sorted by ``fact_id``.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from openfinance.canonical.concept import Concept, concept_from_clark
from openfinance.canonical.errors import CanonicalContradictionError, CanonicalError
from openfinance.canonical.model import (
    CanonicalDimension,
    Fact,
    FactProvenance,
    fact_id,
    obs_key,
)
from openfinance.canonical.numeric import NumericValue, canonicalize_numeric
from openfinance.canonical.period import CanonicalPeriod, canonicalize_period
from openfinance.canonical.units import CanonicalUnit, canonicalize_unit
from openfinance.canonical.version import CanonicalFactVersion
from openfinance.xbrl.contexts import RawContext
from openfinance.xbrl.model import RawDocument, RawFact
from openfinance.xbrl.parser import ParsedInstance
from openfinance.xbrl.units import RawUnit

__all__ = ["CanonicalizeResult", "Canonicalizer"]


@dataclass(frozen=True, slots=True)
class CanonicalizeResult:
    """The deterministic outcome of canonicalizing one parsed instance.

    ``facts`` are sorted by ``fact_id``. The counts make the "no silent drops"
    guarantee auditable (requirement 16): ``raw_fact_count`` is the number of
    input raw facts; ``fact_count`` the number of canonical Facts;
    ``collapsed_duplicate_count`` the number of raw facts that collapsed into an
    already-seen Fact (``raw_fact_count - fact_count``). Nothing is ever dropped.
    """

    raw_document_id: str
    facts: tuple[Fact, ...]
    raw_fact_count: int

    @property
    def fact_count(self) -> int:
        return len(self.facts)

    @property
    def collapsed_duplicate_count(self) -> int:
        return self.raw_fact_count - self.fact_count


class Canonicalizer:
    """Turn Phase 3 raw facts into deterministic canonical :class:`Fact` records."""

    def __init__(self, *, version: CanonicalFactVersion | None = None) -> None:
        self._version = version or CanonicalFactVersion()

    @property
    def version(self) -> CanonicalFactVersion:
        return self._version

    def canonicalize(self, parsed: ParsedInstance) -> CanonicalizeResult:
        """Canonicalize one parsed instance into its canonical Facts.

        Deterministic and fail-closed: raises
        :class:`~openfinance.canonical.errors.CanonicalError` (or its
        contradiction subclass) rather than fabricate or drop a value.
        """
        return self.canonicalize_records(
            document=parsed.document,
            contexts=parsed.contexts,
            units=parsed.units,
            facts=parsed.facts,
        )

    def canonicalize_records(
        self,
        *,
        document: RawDocument,
        contexts: dict[str, RawContext],
        units: dict[str, RawUnit],
        facts: tuple[RawFact, ...],
    ) -> CanonicalizeResult:
        """Canonicalize raw records directly (e.g. read back from the raw store).

        Equivalent to :meth:`canonicalize` but accepts the constituent records so
        a caller can canonicalize what the Phase 3
        :meth:`~openfinance.xbrl.store.RawXbrlStore.read_instance` returns without
        reconstructing a :class:`ParsedInstance`.
        """
        version_id = self._version.transformation_version_id
        # Map a fact's structural unit_ref -> its RawUnit. Structurally identical
        # units share a ref, so any representative is correct; "" (no unit) maps
        # to None (a non-numeric fact) via canonicalize_unit(None).
        unit_by_ref: dict[str, RawUnit] = {u.unit_ref(): u for u in units.values()}

        # Group raw facts by their canonical fact_id (i.e. by obs_key within this
        # filing + transformation version). Each group becomes at most one Fact.
        groups: dict[str, list[tuple[RawFact, _Canonical]]] = {}
        order: list[str] = []
        for raw in facts:
            context = contexts.get(raw.context_ref)
            if context is None:
                # Phase 3 guarantees every fact resolves to a context; a miss
                # here means corrupted derived state — fail closed, never guess.
                raise CanonicalError(
                    f"raw fact {raw.raw_fact_id} references unknown context "
                    f"{raw.context_ref!r}"
                )
            canonical = self._canonicalize_one(
                raw, context, unit_by_ref.get(raw.unit_ref)
            )
            if canonical.fact_id not in groups:
                groups[canonical.fact_id] = []
                order.append(canonical.fact_id)
            groups[canonical.fact_id].append((raw, canonical))

        built = [self._build_fact(document, version_id, groups[fid]) for fid in order]
        built.sort(key=lambda f: f.fact_id)
        return CanonicalizeResult(
            raw_document_id=document.raw_document_id,
            facts=tuple(built),
            raw_fact_count=len(facts),
        )

    def _canonicalize_one(
        self, raw: RawFact, context: RawContext, unit: RawUnit | None
    ) -> _Canonical:
        """Compute the canonical projection of one raw fact (no grouping yet)."""
        concept = concept_from_clark(raw.concept)
        period = canonicalize_period(context)
        canonical_unit = canonicalize_unit(unit)
        numeric = canonicalize_numeric(raw)

        key = obs_key(
            company_id=raw.provenance.company_id,
            security_id=None,  # deferred: no external security master (recon)
            concept_clark=concept.clark,
            period_type=period.period_type.value,
            period_start=period.period_start,
            period_end=period.period_end,
            unit_ref=raw.unit_ref,  # raw structural ref — never the canonical token
            dimensions_hash=raw.dimensions_hash,
        )
        fid = fact_id(
            transformation_version_id=self._version.transformation_version_id,
            filing_id=raw.provenance.filing_id,
            obs_key_value=key,
        )
        return _Canonical(
            fact_id=fid,
            obs_key=key,
            concept=concept,
            period=period,
            unit=canonical_unit,
            raw_unit=unit,
            numeric=numeric,
            dimensions=tuple(
                CanonicalDimension(
                    axis=d.axis,
                    member=d.member,
                    is_typed=d.is_typed,
                    typed_child=d.typed_child,
                    typed_text=d.typed_text,
                )
                for d in context.dimensions
            ),
        )

    def _build_fact(
        self,
        document: RawDocument,
        version_id: str,
        members: list[tuple[RawFact, _Canonical]],
    ) -> Fact:
        """Reduce a group of raw facts sharing one obs_key to a single Fact.

        A genuine duplicate (identical canonical value) collapses; same-obs_key
        *precision variants* (the same value at different ``decimals``) collapse to
        the most-precise member per the resolved policy (open-question 8); an
        irreconcilable value contradiction fails closed (§13 case 8). Within the
        collapsing cases the deterministic representative is the member selected by
        :meth:`_select_representative`; provenance lists every contributing raw
        fact regardless.
        """
        # Deterministic base ordering (also the tie-break within equal precision).
        members = sorted(members, key=lambda m: (m[0].ordinal, m[0].raw_fact_id))
        representative_raw, canonical = self._select_representative(members)

        raw_fact_ids = tuple(sorted(raw.raw_fact_id for raw, _ in members))
        provenance = FactProvenance(
            raw_fact_id=representative_raw.raw_fact_id,
            raw_fact_ids=raw_fact_ids,
            raw_document_id=document.raw_document_id,
            filing_id=representative_raw.provenance.filing_id,
            accession=representative_raw.provenance.accession,
            company_id=representative_raw.provenance.company_id,
            source_artifact_sha256=representative_raw.provenance.source_artifact_sha256,
            source_url=representative_raw.provenance.source_url,
            source_document_name=representative_raw.provenance.source_document_name,
            transformation_version_id=version_id,
        )

        raw_unit = canonical.raw_unit
        return Fact(
            fact_id=canonical.fact_id,
            obs_key=canonical.obs_key,
            company_id=representative_raw.provenance.company_id,
            security_id=None,
            concept=canonical.concept,
            taxonomy=canonical.concept.taxonomy,
            period_type=canonical.period.period_type,
            period_start=canonical.period.period_start,
            period_end=canonical.period.period_end,
            value_numeric_str=canonical.numeric.value_numeric_str,
            value_text=canonical.numeric.value_text,
            is_nil=representative_raw.is_nil,
            unit=canonical.unit.token,
            currency=canonical.unit.currency,
            unit_ref=representative_raw.unit_ref,
            unit_numerator=raw_unit.numerator if raw_unit is not None else (),
            unit_denominator=raw_unit.denominator if raw_unit is not None else (),
            unit_is_divide=raw_unit.is_divide if raw_unit is not None else False,
            scale=canonical.numeric.scale,
            decimals=canonical.numeric.decimals,
            raw_value=representative_raw.value_raw,
            raw_scale=representative_raw.scale,
            raw_sign=representative_raw.sign,
            raw_decimals=representative_raw.decimals,
            dimensions=canonical.dimensions,
            dimensions_hash=representative_raw.dimensions_hash,
            filing_id=representative_raw.provenance.filing_id,
            transformation_version_id=version_id,
            provenance=provenance,
        )

    def _select_representative(
        self, members: list[tuple[RawFact, _Canonical]]
    ) -> tuple[RawFact, _Canonical]:
        """Pick the canonical member for a same-obs_key group, or fail closed.

        ``members`` is pre-sorted by ``(ordinal, raw_fact_id)`` (the deterministic
        tie-break). Cases:

        * All members share one canonical value signature → genuine duplicate;
          return the first (lowest ordinal).
        * Members differ only by ``decimals`` precision and every value is a
          consistent rounding of the single most-precise value → precision variant
          (open-question 8): return the most-precise member (ties broken by the
          base ordering). All raw facts are still retained in provenance.
        * Otherwise (a real value disagreement, a nil-vs-number mismatch, or a
          member whose ``decimals`` cannot be read) → fail closed.
        """
        first_raw, first_canonical = members[0]
        signature = _value_signature(first_canonical.numeric, first_raw)
        if all(_value_signature(c.numeric, r) == signature for r, c in members[1:]):
            return first_raw, first_canonical
        return self._reconcile_precision(members)

    def _reconcile_precision(
        self, members: list[tuple[RawFact, _Canonical]]
    ) -> tuple[RawFact, _Canonical]:
        """Reconcile a group whose members disagree on value as precision variants.

        Every member must be numeric (nil / non-numeric text can never be a
        rounding of a number), carry a readable integer ``decimals``, and equal the
        most-precise member's value rounded to its own ``decimals``. If so the
        most-precise member is the representative; otherwise we fail closed — we
        never arbitrate a genuine data-quality contradiction (§13 case 8).
        """
        readings: list[tuple[int, Decimal, RawFact, _Canonical]] = []
        for raw, canonical in members:
            num = canonical.numeric
            # A rounding relationship is only defined between plain numbers.
            if raw.is_nil or num.value_numeric_str is None or num.decimals is None:
                raise self._contradiction(members)
            readings.append(
                (num.decimals, Decimal(num.value_numeric_str), raw, canonical)
            )

        # Most precise = largest `decimals` (XBRL: higher decimals ⇒ finer).
        # The base (ordinal, raw_fact_id) order already applied to `members` makes
        # ties deterministic since `max` returns the first maximal element.
        best_decimals = max(d for d, _, _, _ in readings)
        best = next(r for r in readings if r[0] == best_decimals)
        _, best_value, best_raw, best_canonical = best

        for decimals, value, _, _ in readings:
            if _round_to_decimals(best_value, decimals) != value:
                raise self._contradiction(members)
        return best_raw, best_canonical

    @staticmethod
    def _contradiction(
        members: list[tuple[RawFact, _Canonical]],
    ) -> CanonicalContradictionError:
        first_raw, first_canonical = members[0]
        others = ", ".join(r.raw_fact_id for r, _ in members[1:])
        return CanonicalContradictionError(
            "same observation key with irreconcilable values within one filing "
            f"(obs_key derived fact_id {first_canonical.fact_id}): "
            f"{first_raw.raw_fact_id} vs {others}; the values are neither identical "
            "nor consistent roundings of a single most-precise value — refusing to "
            "arbitrate a data-quality contradiction"
        )


def _round_to_decimals(value: Decimal, decimals: int) -> Decimal:
    """Round ``value`` to XBRL ``decimals`` precision (half-up), exactly.

    ``decimals`` counts digits right of the point, so the rounding unit is
    ``10**-decimals`` (e.g. ``decimals=-6`` rounds to the nearest million). Uses
    :class:`Decimal` throughout, so no binary-float drift is introduced.
    """
    quantum = Decimal(10) ** (-decimals)
    return (value / quantum).quantize(Decimal(1), rounding=ROUND_HALF_UP) * quantum


def _value_signature(
    numeric: NumericValue, raw: RawFact
) -> tuple[bool, str | None, str | None]:
    """A comparable signature of a fact's canonical value for duplicate/contradiction.

    ``(is_nil, value_numeric_str, value_text)`` — nil, the base-unit numeric
    string, and the non-numeric text fully characterize the canonical value, so
    two raw facts with the same obs_key are a genuine duplicate iff their
    signatures are equal (nil ≠ zero falls out naturally: nil has ``is_nil=True``
    and a ``None`` value, zero has ``is_nil=False`` and ``"0"``).
    """
    return (raw.is_nil, numeric.value_numeric_str, numeric.value_text)


@dataclass(frozen=True, slots=True)
class _Canonical:
    """Internal: the canonical projection of one raw fact, pre-grouping."""

    fact_id: str
    obs_key: str
    concept: Concept
    period: CanonicalPeriod
    unit: CanonicalUnit
    raw_unit: RawUnit | None
    numeric: NumericValue
    dimensions: tuple[CanonicalDimension, ...]
