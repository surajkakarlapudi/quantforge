"""The declarative universe-construction specification (Phase 9.2).

A :class:`UniverseSpecification` is the *reproducible statement of intent* for a
constructed universe: a name, a specification version, and an **ordered** list of
:class:`~quantforge.universe.filters.UniverseFilter` selection rules. It is a pure,
immutable, serializable value — it holds **no** resolved companies, no boundary, and
no data. Evaluating it is the :class:`~quantforge.universe.builder.UniverseBuilder`'s
job; the specification only says *what* to build, never *when* or *against which
snapshot*.

Splitting the request (this) from the evaluation (the builder) from the result (a
:class:`~quantforge.universe.model.Universe`) is the same discipline the metric and
factor layers use — a versioned definition, a fail-closed engine, and a
content-addressed result — and it is what makes a construction reproducible: the
same specification re-run under the same builder over the same data yields the same
universe (§12).

``specification_id`` is a content hash over the name, the specification version, and
the ordered filter ids, so it pins *only* the request and is independent of any data
or boundary — two identical specifications always share it. An empty filter list
fails closed (:class:`~quantforge.universe.errors.UniverseSpecificationError`): a
construction that selects on nothing is a bug, not a request for "everyone" (there is
no implicit universe, mirroring Phase 8's Decision F1).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from quantforge.universe.errors import UniverseSpecificationError
from quantforge.universe.filters import UniverseFilter, filter_from_dict
from quantforge.universe.identity import specification_id as _specification_id

__all__ = ["SPECIFICATION_VERSION", "UniverseSpecification"]

# The specification *schema* version — bump it when the meaning of a specification's
# serialized shape changes (not when construction *logic* changes; that is the
# builder's UNIVERSE_CONSTRUCTION_VERSION). Recorded in provenance and hashed into
# specification_id so a specification authored under one schema cannot be confused
# with one authored under another.
SPECIFICATION_VERSION = "universe-spec/1"


@dataclass(frozen=True, slots=True)
class UniverseSpecification:
    """An immutable, ordered set of construction rules — the *request* (§9.2).

    Attributes
    ----------
    name:
        A human-facing label for the construction (e.g. ``"large-cap-tech"``). Part
        of identity — renaming a specification yields a new ``specification_id`` — so
        two constructions with different intents never share an id.
    filters:
        The ordered selection rules. The **first** must be a *source*
        (:class:`~quantforge.universe.filters.ExplicitCompanyFilter`), because a
        narrowing rule has nothing to narrow until membership is established; this is
        validated at construction time. Later filters narrow, in declared order.
    spec_version:
        The specification-schema version (defaults to :data:`SPECIFICATION_VERSION`).
    """

    name: str
    filters: tuple[UniverseFilter, ...]
    spec_version: str = field(default=SPECIFICATION_VERSION)

    def __post_init__(self) -> None:
        if not self.name:
            raise UniverseSpecificationError(
                "a universe specification must have a non-empty name"
            )
        if not self.filters:
            raise UniverseSpecificationError(
                "a universe specification must declare at least one filter; a "
                "construction that selects on nothing is a bug, not 'everyone'"
            )
        if not self.filters[0].is_source:
            raise UniverseSpecificationError(
                "the first filter must be an explicit source "
                "(ExplicitCompanyFilter); a narrowing filter has no membership to "
                "narrow until an explicit source establishes it — there is no "
                "implicit universe"
            )

    @property
    def filter_ids(self) -> tuple[str, ...]:
        """The ordered content-addressed ids of the declared filters."""
        return tuple(f.filter_id for f in self.filters)

    @property
    def specification_id(self) -> str:
        """Content hash over name + version + ordered filter ids (§9.2)."""
        return _specification_id(
            name=self.name,
            spec_version=self.spec_version,
            filter_ids=self.filter_ids,
        )

    def to_dict(self) -> dict[str, object]:
        """A deterministic, serializable declaration (round-trips via from_dict)."""
        return {
            "name": self.name,
            "spec_version": self.spec_version,
            "specification_id": self.specification_id,
            "filters": [f.to_dict() for f in self.filters],
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> UniverseSpecification:
        """Reconstruct a specification from its serialized declaration.

        Rebuilds each filter via
        :func:`~quantforge.universe.filters.filter_from_dict` (fail-closed on an
        unknown or malformed filter), then re-validates the whole specification (so a
        tampered serialization cannot yield an invalid specification).
        """
        name = raw.get("name")
        if not isinstance(name, str):
            raise UniverseSpecificationError("specification 'name' must be a string")
        filters_raw = raw.get("filters")
        if not isinstance(filters_raw, list):
            raise UniverseSpecificationError("specification 'filters' must be a list")
        filters: list[UniverseFilter] = []
        for item in filters_raw:
            if not isinstance(item, dict):
                raise UniverseSpecificationError(
                    "each specification filter must be an object"
                )
            filters.append(filter_from_dict(item))
        spec_version = raw.get("spec_version", SPECIFICATION_VERSION)
        if not isinstance(spec_version, str):
            raise UniverseSpecificationError(
                "specification 'spec_version' must be a string"
            )
        return cls(name=name, filters=tuple(filters), spec_version=spec_version)
