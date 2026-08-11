"""The portfolio-optimization orchestration engine (§6, §12, PO-1..PO-5).

:class:`PortfolioOptimizationEngine` sits strictly **above** Phase 20: it is a pure
consumer that turns a declarative
:class:`~quantforge.optimization.spec.PortfolioOptimizationSpecification` into a sealed
:class:`~quantforge.optimization.result.PortfolioOptimization` by *resolving* the one
already-sealed :class:`~quantforge.factorrisk.result.FactorRiskModel` a request names,
*verifying* it, *reconstructing* the full symmetric ``N x N`` factor covariance matrix
from its sealed upper-triangle covariance cells, *solving* the fully-invested global
minimum-variance (GMV) problem over that matrix under the pinned decimal context, and
sealing the answer. It introduces no new data-resolution logic, no new PIT surface, and
no new store: the risk model was sealed ex-post over PIT-walked factor portfolios by
Phase 20, and the optimization persists write-once to the shared research sidecar (§6,
§13, §16).

The build (§6):

1. **Resolve** the ``factor_risk_id`` from the shared sidecar via
   ``store.read_as(id, FactorRiskModel.from_dict)``. A missing id (or a payload that
   does not decode as a ``FactorRiskModel``) is a consistency defect - we refuse to
   optimize an artifact we cannot materialize - and raises
   :class:`~quantforge.optimization.errors.PortfolioOptimizationConsistencyError` (fail
   closed, PO-1/PO-3).
2. **Verify** the resolved record: its ``research_result_id`` equals the requested id (a
   corrupt sidecar whose key disagrees with its content), and its sealed ``result_hash``
   is folded into the optimization's identity, so the optimization's id is transitively
   sensitive to any change in the risk model - and, through it, any factor or corpus
   (PO-1). The factor count must lie in ``2..N_MAX`` (the same bound Phase 20 enforces;
   re-checked here fail-closed, PO-1).
3. **Reconstruct** the full symmetric covariance matrix ``Σ`` from the record's
   upper-triangle :class:`~quantforge.factorrisk.model.CovarianceCell` tuple: every
   ``i <= j`` per-period cell must be present, KNOWN, and a finite decimal string
   (guaranteed by Phase 20's construction; re-verified here, a corrupt / UNDEFINED /
   missing cell raising, PO-3). ``Σ`` is filled symmetrically (``Σ[j][i] = Σ[i][j]``);
   the covariance matrix is **never** repaired, regularized, or altered (PO-4).
4. **Solve** the fully-invested GMV closed form
   (:func:`~quantforge.optimization.solve.solve_min_variance`) under the pinned decimal
   context - the exact-``Decimal`` LDLᵀ solve of ``Σx = 1``, the normalization
   ``w = x/Σx``, and the quadratic form ``wᵀΣw`` for the achieved per-period variance
   and its volatility. A non-positive-definite ``Σ`` is returned as a first-class
   UNDEFINED ``SINGULAR_COVARIANCE`` result, never a divide-by-zero (PO-4).
5. **Seal** the computed blocks into a
   :class:`~quantforge.optimization.result.PortfolioOptimization` (its ``result_hash``
   folds the answer) and persist it write-once to the same sidecar. Rebuilding an
   identical request is a byte-identical no-op; a differing payload under the same id
   fails closed via the store's guard.

The engine holds no mutable per-run state - a build's state lives entirely in local
variables, so one engine can compute many records and two builds of the same spec over
the same immutable sidecar are byte-identical.
"""

from __future__ import annotations

from decimal import Context

from quantforge.factorrisk.model import FactorRiskStatus
from quantforge.factorrisk.result import FactorRiskModel
from quantforge.factorrisk.spec import N_MAX
from quantforge.factors.store import ResearchResultStore
from quantforge.optimization.errors import (
    PortfolioOptimizationConfigurationError,
    PortfolioOptimizationConsistencyError,
)
from quantforge.optimization.model import (
    WeightCell,
    factor_label,
)
from quantforge.optimization.result import (
    BOUNDARY_PIT,
    COVARIANCE_BASIS_PER_PERIOD,
    PortfolioOptimization,
)
from quantforge.optimization.solve import solve_min_variance
from quantforge.optimization.spec import PortfolioOptimizationSpecification
from quantforge.optimization.version import PortfolioOptimizationEngineVersion
from quantforge.workspace import Workspace

__all__ = ["PortfolioOptimizationEngine"]

#: The minimum number of factors the optimizer accepts - the same lower bound Phase 20's
#: risk model enforces. A single-factor "portfolio" has the trivial GMV ``w = 1`` and no
#: cross-factor structure; the fully-invested optimization is only meaningful over a
#: pair or more. Re-checked here fail-closed (PO-1).
_MIN_FACTORS = 2


class PortfolioOptimizationEngine:
    """Resolve, verify, reconstruct, solve, and seal an optimization request (§6).

    Constructed from a :class:`~quantforge.workspace.Workspace` (the composition root);
    it reuses the workspace's shared Phase 8 research sidecar - the same store the
    factor-risk engine sealed its models to - so a request optimizes exactly the risk
    model already present. The sidecar may be overridden (for tests). The engine pins
    its solve logic + method + decimal context via
    :class:`PortfolioOptimizationEngineVersion`, and computes every value under that
    version's decimal context.
    """

    def __init__(
        self,
        workspace: Workspace,
        *,
        research_store: ResearchResultStore | None = None,
        version: PortfolioOptimizationEngineVersion | None = None,
    ) -> None:
        self._workspace = workspace
        self._research_store = research_store
        self._version = (
            version if version is not None else PortfolioOptimizationEngineVersion()
        )

    @property
    def optimization_engine_version_id(self) -> str:
        """The solve-logic + method + decimal-context version folded into every id."""
        return self._version.optimization_engine_version_id

    @property
    def research_store(self) -> ResearchResultStore:
        """The write-once sidecar the optimization resolves from and persists to."""
        if self._research_store is not None:
            return self._research_store
        store = self._workspace.research_result_store
        assert isinstance(store, ResearchResultStore)
        return store

    def optimize(
        self, spec: PortfolioOptimizationSpecification
    ) -> PortfolioOptimization:
        """Resolve, verify, reconstruct, solve, seal, and persist from ``spec`` (§6).

        Deterministic and reproducible: the same spec over the same immutable sidecar
        re-resolves the same risk model, reconstructs the same ``Σ``, recomputes
        byte-identical weights / variance / volatility under the pinned decimal context,
        and seals a byte-identical
        :class:`~quantforge.optimization.result.PortfolioOptimization` on any machine
        (whose sidecar write is an idempotent no-op). Fails closed on a missing /
        drifted reference, a non-``FactorRiskModel`` payload, a factor count outside
        ``2..N_MAX``, or a corrupt covariance cell; a non-positive-definite
        covariance is recorded as a first-class UNDEFINED ``SINGULAR_COVARIANCE``
        result (PO-4), never raised.
        """
        if not isinstance(spec, PortfolioOptimizationSpecification):
            raise PortfolioOptimizationConfigurationError(
                "optimize() requires a PortfolioOptimizationSpecification"
            )

        store = self.research_store
        context = self._version.decimal_context()

        # -- resolve + verify the referenced risk model (PO-1/PO-3) -----------
        model = self._resolve(spec.factor_risk_id, store)
        n = len(model.factors)
        if not (_MIN_FACTORS <= n <= N_MAX):
            raise PortfolioOptimizationConsistencyError(
                f"the referenced factor-risk model declares {n} factor(s), outside the "
                f"supported range {_MIN_FACTORS}..{N_MAX}; fail closed rather than "
                "optimize a degenerate or oversized covariance matrix"
            )

        # -- reconstruct the full symmetric covariance matrix Σ (PO-3/PO-4) ---
        sigma = self._reconstruct_covariance(model, n, context)

        # -- solve the fully-invested GMV under the pinned context (PO-4) -----
        solution = solve_min_variance(sigma, context=context)

        # -- carry provenance from the referenced model, seal, persist -------
        labels = tuple(factor_label(i) for i in range(n))
        weights = tuple(
            WeightCell(label=labels[i], value=solution.weights[i]) for i in range(n)
        )
        optimization = PortfolioOptimization.seal(
            optimization_engine_version_id=(
                self._version.optimization_engine_version_id
            ),
            optimization_spec=spec.to_dict(),
            objective=spec.objective,
            constraint_spec={"fully_invested": spec.fully_invested},
            covariance_basis=COVARIANCE_BASIS_PER_PERIOD,
            risk_model_ref=(model.research_result_id, model.result_hash),
            boundary_kind=BOUNDARY_PIT,
            schedule_id=model.schedule_id,
            factor_portfolio_engine_version_id=(
                model.factor_portfolio_engine_version_id
            ),
            n_factors=n,
            factor_labels=labels,
            status=solution.status,
            weights=weights,
            portfolio_variance=solution.variance,
            portfolio_volatility=solution.volatility,
            dataset_version_ids=model.dataset_version_ids,
            market_dataset_version_ids=model.market_dataset_version_ids,
            formula_version=self._version.solve_version,
        )
        # Persist write-once to the shared research sidecar. Idempotent for a
        # byte-identical re-build; a differing payload under the same id raises there.
        store.write(optimization)
        return optimization

    # -- resolution & verification -------------------------------------------

    def _resolve(
        self, factor_risk_id: str, store: ResearchResultStore
    ) -> FactorRiskModel:
        """Read + verify the referenced risk model from the sidecar (fail closed).

        Verifies the fail-closed consistency guards (PO-1/PO-3): the id is present; the
        stored payload decodes as a
        :class:`~quantforge.factorrisk.result.FactorRiskModel` (a payload that is not a
        risk model - e.g. a factor portfolio id passed by mistake - fails ``from_dict``
        and is refused, never optimized); and the resolved record's own
        ``research_result_id`` equals the requested id (a corrupt sidecar
        whose key disagrees with its content). The referenced model's ``result_hash`` is
        folded into the optimization identity (PO-1), so any change to it changes the
        optimization's id. The PIT boundary needs no runtime check: a
        ``FactorRiskModel`` is ex-post over PIT-walked factor portfolios by
        construction, so the sealed optimization carries the explicit
        ``boundary_kind = "pit"`` unconditionally, documenting the input side; the
        optimization output remains ex-post and non-PIT (PO-2).
        """
        try:
            result = store.read_as(factor_risk_id, FactorRiskModel.from_dict)
        except (KeyError, ValueError) as exc:
            raise PortfolioOptimizationConsistencyError(
                f"factor-risk model {factor_risk_id!r} could not be decoded as a "
                "FactorRiskModel; the referenced artifact is absent or not a risk "
                "model (fail closed)"
            ) from exc
        if result is None:
            raise PortfolioOptimizationConsistencyError(
                f"factor-risk model {factor_risk_id!r} is not present in the research "
                "sidecar; cannot optimize an artifact that was never sealed (fail "
                "closed)"
            )
        if result.research_result_id != factor_risk_id:
            raise PortfolioOptimizationConsistencyError(
                f"factor-risk model {factor_risk_id!r} resolved to a record whose id "
                f"{result.research_result_id!r} disagrees with the request; the "
                "sidecar is inconsistent (fail closed)"
            )
        return result

    def _reconstruct_covariance(
        self, model: FactorRiskModel, n: int, context: Context
    ) -> list[list[str]]:
        """Rebuild the full symmetric ``N x N`` covariance matrix ``Σ`` (PO-3/PO-4).

        Phase 20 seals only the **upper triangle** (``i <= j``) of the per-period
        covariance, each cell KNOWN by construction. This fills a dense ``N x N`` matrix
        of decimal strings from those cells, mirroring each ``Σ[i][j]`` into ``Σ[j][i]``
        by symmetry. It re-verifies fail-closed (never trusting the sealed record
        blindly, PO-3): every index is in range with ``i <= j``, no upper-triangle
        position is missing or set twice, and every used cell is KNOWN with a string
        value (an UNDEFINED or non-string covariance cell is corrupt and raises).
        The matrix is
        **never** repaired, regularized, or altered - a non-positive-definite ``Σ`` is
        the solve layer's UNDEFINED ``SINGULAR_COVARIANCE`` concern (PO-4), not this
        layer's to fix.
        """
        matrix: list[list[str | None]] = [[None] * n for _ in range(n)]
        for cell in model.covariance:
            i, j = cell.i, cell.j
            if not (0 <= i < n and 0 <= j < n) or i > j:
                raise PortfolioOptimizationConsistencyError(
                    f"covariance cell ({i}, {j}) is not a valid upper-triangle index "
                    f"for a {n}-factor model; the referenced risk model is corrupt "
                    "(fail closed)"
                )
            if cell.value.status is not FactorRiskStatus.KNOWN:
                raise PortfolioOptimizationConsistencyError(
                    f"covariance cell ({i}, {j}) is UNDEFINED; a factor-risk model's "
                    "per-period covariance cells must all be KNOWN by construction, so "
                    "an UNDEFINED cell is a corrupt input (fail closed)"
                )
            value = cell.value.value
            if not isinstance(value, str):
                raise PortfolioOptimizationConsistencyError(
                    f"covariance cell ({i}, {j}) carries a non-string value; the "
                    "referenced risk model is corrupt (fail closed)"
                )
            if matrix[i][j] is not None:
                raise PortfolioOptimizationConsistencyError(
                    f"covariance cell ({i}, {j}) appears more than once; the "
                    "referenced risk model is corrupt (fail closed)"
                )
            matrix[i][j] = value
            matrix[j][i] = value

        for i in range(n):
            for j in range(n):
                if matrix[i][j] is None:
                    raise PortfolioOptimizationConsistencyError(
                        f"covariance cell ({min(i, j)}, {max(i, j)}) is missing; the "
                        f"referenced risk model does not fully cover the {n}x{n} "
                        "covariance matrix (fail closed)"
                    )

        # Every cell is now a non-None string; narrow for the solve layer. The parse to
        # Decimal (and the finite-ness check) happens inside solve_min_variance, so a
        # non-finite string is caught there fail-closed.
        return [[_require(matrix[i][j]) for j in range(n)] for i in range(n)]


def _require(value: str | None) -> str:
    """Assert a covariance cell was filled - a programming-bug backstop, never data."""
    assert value is not None  # guaranteed by the full-coverage check above
    return value
