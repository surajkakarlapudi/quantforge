"""The declarative, content-addressed net-of-cost-significance request (§14).

A **net-of-cost-significance request** names exactly one sealed
:class:`~quantforge.netcost.result.NetOfCostPerformance` to test. Like every request in
this project it is a frozen value whose identity is a pure content hash of *what was
declared* - the engine resolves and interprets it; it never executes caller code
(mirrors :class:`~quantforge.calsig.spec.CalibrationSignificanceSpecification`).

The spec validates its own shape at construction (fail closed,
:class:`~quantforge.netcostsig.errors.NetCostSigConfigurationError`): an empty ``name``
/ ``spec_version`` / ``source_net_of_cost_id``. It reads no store and no wall clock - it
cannot know whether the referenced net-of-cost record exists (that is the engine's
fail-closed resolution step) or whether it is MEASURED; it validates only the request's
internal shape.

There is **no** per-request numerical parameter: the null mean tested is the fixed
platform constant :data:`~quantforge.netcostsig.result.NULL_MEAN_RETURN` (``0`` - a
strategy with no after-cost edge earns zero, folded into the id by the identity, not the
request), and the method is the single approved one-sample large-sample upper-tailed
test. So a significance request is fully described by the name and the one source id -
the simplest request in the research spine, alongside the calibration-significance
request it mirrors.
"""

from __future__ import annotations

from dataclasses import dataclass

from quantforge.netcostsig.errors import NetCostSigConfigurationError
from quantforge.netcostsig.version import NETCOSTSIG_SPEC_VERSION

__all__ = ["NetOfCostSignificanceSpecification"]


@dataclass(frozen=True, slots=True)
class NetOfCostSignificanceSpecification:
    """A declarative, content-addressed net-of-cost-significance request.

    ``source_net_of_cost_id`` is the ``research_result_id`` of exactly one sealed
    :class:`~quantforge.netcost.result.NetOfCostPerformance`. Constructing this reads no
    store and no wall clock; it validates its own shape, exactly as the calibration-
    significance layer refuses a misconfigured request.
    """

    name: str
    source_net_of_cost_id: str
    spec_version: str = NETCOSTSIG_SPEC_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name:
            raise NetCostSigConfigurationError(
                "a net-of-cost-significance request must have a non-empty name"
            )
        if (
            not isinstance(self.source_net_of_cost_id, str)
            or not self.source_net_of_cost_id
        ):
            raise NetCostSigConfigurationError(
                "source_net_of_cost_id must be a non-empty net-of-cost id"
            )
        if not isinstance(self.spec_version, str) or not self.spec_version:
            raise NetCostSigConfigurationError(
                "spec_version must be a non-empty string"
            )

    def to_dict(self) -> dict[str, object]:
        """The canonical request payload (deterministic; embedded in the sealed
        record)."""
        return {
            "spec_version": self.spec_version,
            "name": self.name,
            "source_net_of_cost_id": self.source_net_of_cost_id,
        }
