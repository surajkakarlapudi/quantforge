"""Versioned availability rules & reproducible snapshots (data-model §9, §PA.2).

Two immutable, content-addressed versioning entities live here, both mirroring the
Phase 4 :class:`~quantforge.canonical.version.CanonicalFactVersion` pattern (id is
a ``sha256:`` hash of the content; nothing depends on the wall clock):

* :class:`AvailabilityPolicy` — the **versioned, form-scoped, era-bounded rule**
  that ``derive(evidence, policy)`` (see :mod:`quantforge.availability.policy`)
  applies to turn filing evidence into an availability triple. Its
  ``rule_definition`` is *declarative data* (:class:`AvailabilityRule`): a cutoff,
  a business calendar, an evidence-precedence flag, and the fail-closed switch —
  so the rule is auditable and every change is a **new version, never a mutation**
  (invariant 14). ``availability_policy_id = hash(policy_id, policy_version,
  rule_definition_hash)``.
* :class:`DatasetVersion` — the immutable content-addressed **manifest** (a Merkle
  root over the sorted member id lists + transformation version + sorted policy
  set) that makes both ``PIT`` and ``REVISED`` resolutions reproducible: pinning a
  ``dataset_version_id`` pins exactly which facts, which normalizer, and which
  availability policies produced an answer (§9, invariant 19).

The initial policy is created by :func:`edgar_std_v1`: ``policy_id="edgar-std"``,
``policy_version="v1"``, ``status=provisional``, ``confidence=unvalidated`` — it
derives conservatively and, per the Phase 5 mandate, can only ever produce
``derived`` or ``unknown`` (never ``verified``) until real dissemination evidence
and a validated successor policy exist.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum

from quantforge.availability.calendar import EASTERN_DST_REGIME_FROM
from quantforge.sec.artifacts import sha256_hex

__all__ = [
    "AvailabilityPolicy",
    "AvailabilityRule",
    "DatasetVersion",
    "PolicyConfidence",
    "PolicyStatus",
    "edgar_std_v1",
    "merkle_root",
]

# A separator that cannot occur in any id component (hashes, qnames, dates are
# all NUL-free), so joined payloads are unambiguous — same convention as §11.
_SEP = "\x00"


class PolicyStatus(StrEnum):
    """Lifecycle state of an :class:`AvailabilityPolicy` version (§9).

    ``PROVISIONAL`` — usable but not yet validated against real SEC filings;
    derives conservatively (§PA.5). ``ACTIVE`` — validated and governing.
    ``DEPRECATED`` — superseded by a later version; retained (never deleted) so
    historical snapshots reproduce.
    """

    ACTIVE = "active"
    PROVISIONAL = "provisional"
    DEPRECATED = "deprecated"


class PolicyConfidence(StrEnum):
    """How well a policy's rules are validated against reality (§9, §PA.5)."""

    VERIFIED_AGAINST_SEC = "verified-against-sec"
    HEURISTIC = "heuristic"
    UNVALIDATED = "unvalidated"


@dataclass(frozen=True, slots=True)
class AvailabilityRule:
    """Declarative definition of how availability is derived (data-model §PA.2).

    This is **data, not code**: ``derive`` reads these fields to decide the
    availability timestamp and status. Because the whole rule is captured here and
    hashed into :attr:`AvailabilityPolicy.availability_policy_id`, any change to
    the rule necessarily produces a new policy version (invariant 14).

    Attributes
    ----------
    rule_kind:
        The derivation algorithm the deriver must apply. The only kind the Phase 5
        deriver implements is ``"acceptance-cutoff-next-business-day"``; any other
        value fails closed
        (:class:`~quantforge.availability.errors.PolicyConfigurationError`) — we
        never guess a rule's intent.
    cutoff_local_time:
        ``"HH:MM"`` wall-clock cutoff in the rule's ``calendar`` timezone (ET). A
        filing accepted at/before this time on a business day is treated as
        available that day; later acceptances roll to the next business day. The
        derived timestamp is conservatively pinned to this cutoff instant (rounds
        *later*, never earlier — §PA.3).
    calendar:
        Business-calendar identifier. Only ``"us-eastern-business"`` is
        implemented (see :mod:`quantforge.availability.calendar`).
    dissemination_evidence_trusted:
        Whether direct dissemination/index evidence may upgrade status to
        ``verified``. **False** in the initial policy (Phase 5 mandate: derived or
        unknown only); a future validated policy version may set it True.
    fail_closed_on_missing_acceptance:
        When acceptance evidence is absent/unusable, produce ``unknown`` rather
        than fall back to filing date or retrieval time. Always True here.
    """

    rule_kind: str = "acceptance-cutoff-next-business-day"
    cutoff_local_time: str = "17:30"
    calendar: str = "us-eastern-business"
    dissemination_evidence_trusted: bool = False
    fail_closed_on_missing_acceptance: bool = True

    def to_dict(self) -> dict[str, object]:
        return {
            "rule_kind": self.rule_kind,
            "cutoff_local_time": self.cutoff_local_time,
            "calendar": self.calendar,
            "dissemination_evidence_trusted": self.dissemination_evidence_trusted,
            "fail_closed_on_missing_acceptance": self.fail_closed_on_missing_acceptance,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> AvailabilityRule:
        return cls(
            rule_kind=_req_str(raw, "rule_kind"),
            cutoff_local_time=_req_str(raw, "cutoff_local_time"),
            calendar=_req_str(raw, "calendar"),
            dissemination_evidence_trusted=bool(
                raw.get("dissemination_evidence_trusted", False)
            ),
            fail_closed_on_missing_acceptance=bool(
                raw.get("fail_closed_on_missing_acceptance", True)
            ),
        )

    @property
    def rule_definition_hash(self) -> str:
        """Deterministic ``sha256:`` hash of the declarative rule content."""
        payload = json.dumps(self.to_dict(), sort_keys=True, ensure_ascii=False).encode(
            "utf-8"
        )
        return f"sha256:{sha256_hex(payload)}"

    @property
    def cutoff_hour_minute(self) -> tuple[int, int]:
        """Parse ``cutoff_local_time`` into ``(hour, minute)``; fail closed if bad."""
        parts = self.cutoff_local_time.split(":")
        if len(parts) != 2:
            raise ValueError(f"invalid cutoff_local_time {self.cutoff_local_time!r}")
        hour, minute = int(parts[0]), int(parts[1])
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError(f"cutoff out of range {self.cutoff_local_time!r}")
        return hour, minute


@dataclass(frozen=True, slots=True)
class AvailabilityPolicy:
    """One immutable, form-scoped, era-bounded availability policy version (§9).

    Selection (§PA.2): a policy governs a filing when the filing's ``form`` is in
    :attr:`form_scope` (or the scope is the wildcard ``"*"``) **and** the filing's
    acceptance date falls in ``[effective_from, effective_to)``. Exactly one
    *active/provisional* version must match a given ``(form, date)``; overlap is a
    configuration error surfaced by the selector.

    Identity is ``availability_policy_id = hash(policy_id, policy_version,
    rule_definition_hash)`` — so two policies with the same logical version but a
    different rule have different ids (they cannot be confused), and re-declaring
    the identical policy reproduces the same id (invariant 20).
    """

    policy_id: str
    policy_version: str
    effective_from: str
    effective_to: str | None
    form_scope: tuple[str, ...]
    rule_definition: AvailabilityRule
    status: PolicyStatus
    confidence: PolicyConfidence
    notes: str = ""

    @property
    def availability_policy_id(self) -> str:
        """``sha256(policy_id, policy_version, rule_definition_hash)`` (§9)."""
        payload = _SEP.join(
            (
                self.policy_id,
                self.policy_version,
                self.rule_definition.rule_definition_hash,
            )
        )
        return f"sha256:{sha256_hex(payload.encode('utf-8'))}"

    def covers_form(self, form: str) -> bool:
        """Whether this policy's form scope covers ``form`` (wildcard-aware)."""
        return "*" in self.form_scope or form in self.form_scope

    def to_dict(self) -> dict[str, object]:
        return {
            "policy_id": self.policy_id,
            "policy_version": self.policy_version,
            "availability_policy_id": self.availability_policy_id,
            "effective_from": self.effective_from,
            "effective_to": self.effective_to,
            "form_scope": list(self.form_scope),
            "rule_definition": self.rule_definition.to_dict(),
            "status": self.status.value,
            "confidence": self.confidence.value,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> AvailabilityPolicy:
        rule_raw = raw["rule_definition"]
        if not isinstance(rule_raw, dict):
            raise ValueError("rule_definition must be an object")
        scope = raw.get("form_scope", [])
        if not isinstance(scope, list) or not all(isinstance(s, str) for s in scope):
            raise ValueError("form_scope must be a list of strings")
        return cls(
            policy_id=_req_str(raw, "policy_id"),
            policy_version=_req_str(raw, "policy_version"),
            effective_from=_req_str(raw, "effective_from"),
            effective_to=_opt_str(raw, "effective_to"),
            form_scope=tuple(scope),
            rule_definition=AvailabilityRule.from_dict(rule_raw),
            status=PolicyStatus(_req_str(raw, "status")),
            confidence=PolicyConfidence(_req_str(raw, "confidence")),
            notes=_str_default(raw, "notes"),
        )


def edgar_std_v1() -> AvailabilityPolicy:
    """The initial availability policy — ``edgar-std/v1`` (Phase 5 mandate).

    Provisional and unvalidated: it encodes the recon-observed convention (recon
    §15 — acceptance UTC + ~17:30 ET cutoff + US business calendar → next business
    day) as a conservative *derived* estimate, and it **never** produces
    ``verified`` (``dissemination_evidence_trusted=False``). Its era is bounded to
    the XBRL mandate onward (``effective_from`` after the 2007 DST regime, so the
    self-contained ET calendar is exactly correct); filings accepted before it get
    ``unknown``. A wildcard form scope makes it the standard default; a future
    form-specific or validated policy is introduced as a *new version*, never an
    edit to this one.
    """
    return AvailabilityPolicy(
        policy_id="edgar-std",
        policy_version="v1",
        # XBRL era; safely after EASTERN_DST_REGIME_FROM so the ET calendar holds.
        effective_from="2009-01-01T00:00:00Z",
        effective_to=None,
        form_scope=("*",),
        rule_definition=AvailabilityRule(),
        status=PolicyStatus.PROVISIONAL,
        confidence=PolicyConfidence.UNVALIDATED,
        notes=(
            "Initial provisional policy. Conservative acceptance-cutoff / "
            "next-business-day derivation from acceptance_timestamp (recon §15); "
            "produces DERIVED or UNKNOWN only, never VERIFIED, until real "
            "dissemination evidence and a validated successor version exist. "
            f"ET calendar valid only from {EASTERN_DST_REGIME_FROM}."
        ),
    )


def merkle_root(leaves: list[str]) -> str:
    """Deterministic Merkle root over ``leaves`` (order-sensitive; sort first).

    Each leaf is hashed, then adjacent hashes are paired and re-hashed up to a
    single root. An odd node at any level is promoted unchanged (a standard
    duplicate-free convention). The empty input has a fixed root (hash of the
    empty string). Deterministic and content-addressed — the basis of
    :attr:`DatasetVersion.dataset_version_id` (invariant 19).
    """
    if not leaves:
        return f"sha256:{sha256_hex(b'')}"
    level = [sha256_hex(leaf.encode("utf-8")) for leaf in leaves]
    while len(level) > 1:
        nxt: list[str] = []
        for i in range(0, len(level), 2):
            if i + 1 < len(level):
                combined = f"{level[i]}{_SEP}{level[i + 1]}".encode()
                nxt.append(sha256_hex(combined))
            else:
                nxt.append(level[i])  # promote the odd tail unchanged
        level = nxt
    return f"sha256:{level[0]}"


@dataclass(frozen=True, slots=True)
class DatasetVersion:
    """An immutable, content-addressed snapshot manifest (data-model §9).

    Pins everything needed to reproduce a ``PIT`` or ``REVISED`` answer: the exact
    fact set, the normalizer version, and the availability-policy set. The id is a
    Merkle root over the (sorted) member id lists plus the transformation version
    and policy set, so any change — one more filing, a re-normalization, a
    re-derived availability under a new policy — yields a new id, and identical
    contents always yield the same id (invariant 19). It is impossible to mutate a
    snapshot without changing its identity.
    """

    transformation_version_id: str
    availability_policy_ids: tuple[str, ...]
    raw_document_ids: tuple[str, ...]
    fact_ids: tuple[str, ...]
    parent_dataset_version_id: str | None = None
    notes: str = ""

    @property
    def dataset_version_id(self) -> str:
        """Merkle root over sorted members + tv id + sorted policy set (§9)."""
        # A tagged, sorted leaf set: sorting makes the id order-independent, and
        # the section tags prevent a fact_id from ever colliding with a
        # raw_document_id or policy id in the leaf space.
        leaves: list[str] = [f"tv{_SEP}{self.transformation_version_id}"]
        leaves += [f"pol{_SEP}{p}" for p in sorted(self.availability_policy_ids)]
        leaves += [f"raw{_SEP}{r}" for r in sorted(self.raw_document_ids)]
        leaves += [f"fact{_SEP}{f}" for f in sorted(self.fact_ids)]
        return merkle_root(leaves)

    def to_dict(self) -> dict[str, object]:
        return {
            "dataset_version_id": self.dataset_version_id,
            "transformation_version_id": self.transformation_version_id,
            "availability_policy_ids": sorted(self.availability_policy_ids),
            "raw_document_ids": sorted(self.raw_document_ids),
            "fact_ids": sorted(self.fact_ids),
            "parent_dataset_version_id": self.parent_dataset_version_id,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> DatasetVersion:
        return cls(
            transformation_version_id=_req_str(raw, "transformation_version_id"),
            availability_policy_ids=_str_tuple(raw, "availability_policy_ids"),
            raw_document_ids=_str_tuple(raw, "raw_document_ids"),
            fact_ids=_str_tuple(raw, "fact_ids"),
            parent_dataset_version_id=_opt_str(raw, "parent_dataset_version_id"),
            notes=_str_default(raw, "notes"),
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


def _str_tuple(raw: dict[str, object], key: str) -> tuple[str, ...]:
    value = raw.get(key, [])
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{key} must be a list of strings")
    return tuple(value)


def _str_default(raw: dict[str, object], key: str) -> str:
    value = raw.get(key, "")
    return value if isinstance(value, str) else ""
