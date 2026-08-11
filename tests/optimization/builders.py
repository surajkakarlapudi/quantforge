"""Offline, obviously-synthetic fixtures for Phase 21 optimization tests.

The optimizer is a pure consumer of one sealed
:class:`~quantforge.factorrisk.result.FactorRiskModel`: it needs only that model's
``N x N`` covariance matrix. Rather than seed a full multi-filer fundamentals + market
corpus and estimate a covariance (that path is proven end-to-end in
``tests/factorrisk``), these builders **synthesize** a sealed ``FactorRiskModel``
directly from a hand-chosen covariance matrix and persist it to a real
:class:`~quantforge.factors.store.ResearchResultStore` sidecar via the workspace. That
gives exact control over the covariance - clean closed-form GMV cases, singular
matrices, and factor counts up to and beyond ``N_MAX`` - while still exercising the
true resolve → verify → reconstruct → solve → seal → persist path through the engine
and the shared store.

The synthesized model is a *valid* sealed record (its ``result_hash`` / id are the real
content hashes, and it round-trips through ``FactorRiskModel.from_dict``), so the
engine's fail-closed reference checks pass exactly as they would for an
engine-estimated model. The covariance moments / correlation cells the optimizer
never reads are filled with honest placeholder KNOWN values. Everything is fictional
and offline (Principle 8).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from quantforge.factorrisk.model import (
    CorrelationCell,
    CovarianceCell,
    CoverageSummary,
    FactorCoverage,
    FactorMoment,
)
from quantforge.factorrisk.model import StatValue as RiskStatValue
from quantforge.factorrisk.model import factor_label as risk_factor_label
from quantforge.factorrisk.result import BOUNDARY_PIT, FactorRiskModel
from quantforge.factorrisk.version import FactorRiskEngineVersion
from quantforge.optimization.engine import PortfolioOptimizationEngine
from quantforge.optimization.spec import PortfolioOptimizationSpecification
from quantforge.workspace import Workspace

__all__ = [
    "DummyRecord",
    "make_opt_spec",
    "make_risk_model",
    "opt_engine",
    "seal_risk_model",
    "workspace",
]

_RISK_ENGINE_VERSION_ID = FactorRiskEngineVersion().factor_risk_engine_version_id


def workspace(root: Path) -> Workspace:
    """A fully-offline workspace rooted at ``root`` (no network, no seeded filers)."""
    return Workspace.open(root)


def opt_engine(ws: Workspace) -> PortfolioOptimizationEngine:
    """The workspace's Phase 21 engine, narrowed from the ``object`` property."""
    engine = ws.optimization_engine
    assert isinstance(engine, PortfolioOptimizationEngine)
    return engine


def _canonical(value: str) -> str:
    """The canonical decimal string of ``value`` (matches Phase 20's sealing)."""
    return str(+Decimal(value))


def make_risk_model(
    matrix: list[list[str]],
    *,
    name: str = "phase21-synthetic-risk",
    periods: int = 4,
    periods_per_year: str = "1",
    schedule_id: str = "schedule-synthetic",
    factor_portfolio_engine_version_id: str = "fpe-synthetic/1",
    dataset_version_ids: tuple[str, ...] = ("ds-synthetic",),
    market_dataset_version_ids: tuple[str, ...] = ("mkt-synthetic",),
) -> FactorRiskModel:
    """Synthesize a sealed :class:`FactorRiskModel` from a full symmetric ``matrix``.

    ``matrix`` is the full ``N x N`` covariance (a list of ``N`` rows of decimal
    strings); only its **upper triangle** is sealed (mirroring Phase 20's D-TRIANGLE
    storage), with each per-period covariance cell KNOWN and its ``annualized``
    companion equal (the ``periods_per_year = "1"`` default). The per-factor moments
    and correlation cells the optimizer never reads are honest KNOWN placeholders.
    Not written to any store - see :func:`seal_risk_model`.
    """
    n = len(matrix)
    assert n >= 1 and all(len(row) == n for row in matrix), "matrix must be square"

    factors = tuple(
        FactorMoment(
            label=risk_factor_label(i),
            mean=RiskStatValue.known("0"),
            volatility=RiskStatValue.known(_canonical(matrix[i][i])),
            annualized_volatility=RiskStatValue.known(_canonical(matrix[i][i])),
        )
        for i in range(n)
    )
    covariance = tuple(
        CovarianceCell(
            i=i,
            j=j,
            value=RiskStatValue.known(_canonical(matrix[i][j])),
            annualized=RiskStatValue.known(_canonical(matrix[i][j])),
        )
        for i in range(n)
        for j in range(i, n)
    )
    correlation = tuple(
        CorrelationCell(i=i, j=j, value=RiskStatValue.known("0"))
        for i in range(n)
        for j in range(i, n)
    )
    coverage = CoverageSummary(
        per_factor=tuple(
            FactorCoverage(
                label=risk_factor_label(i),
                factor_portfolio_id=f"sha256:synthetic-factor-{i}",
                available=periods,
                used=periods,
            )
            for i in range(n)
        ),
        aligned_periods=periods,
        dropped_for_alignment=0,
    )
    factor_refs = tuple(
        (
            risk_factor_label(i),
            f"sha256:synthetic-factor-{i}",
            f"sha256:synthetic-factor-hash-{i}",
        )
        for i in range(n)
    )
    spec_payload: dict[str, object] = {
        "spec_version": "factorrisk/1",
        "name": name,
        "factor_portfolio_ids": [ref[1] for ref in factor_refs],
        "periods_per_year": periods_per_year,
    }
    return FactorRiskModel.seal(
        factor_risk_engine_version_id=_RISK_ENGINE_VERSION_ID,
        factor_risk_spec=spec_payload,
        factor_refs=factor_refs,
        boundary_kind=BOUNDARY_PIT,
        schedule_id=schedule_id,
        factor_portfolio_engine_version_id=factor_portfolio_engine_version_id,
        periods=periods,
        periods_per_year=periods_per_year,
        factors=factors,
        covariance=covariance,
        correlation=correlation,
        coverage=coverage,
        dataset_version_ids=dataset_version_ids,
        market_dataset_version_ids=market_dataset_version_ids,
    )


def seal_risk_model(ws: Workspace, matrix: list[list[str]], **kwargs: object) -> str:
    """Synthesize a risk model, persist it to the workspace sidecar, return its id.

    The returned ``factor_risk_id`` is what a
    :class:`PortfolioOptimizationSpecification` references. Keyword args pass through to
    :func:`make_risk_model`.
    """
    model = make_risk_model(matrix, **kwargs)  # type: ignore[arg-type]
    ws.research_result_store.write(model)
    return model.research_result_id


def make_opt_spec(
    factor_risk_id: str,
    *,
    name: str = "phase21-synthetic",
) -> PortfolioOptimizationSpecification:
    """A minimum-variance, fully-invested request over the given sealed risk model."""
    return PortfolioOptimizationSpecification(name=name, factor_risk_id=factor_risk_id)


@dataclass(frozen=True)
class DummyRecord:
    """A non-``FactorRiskModel`` :class:`ResearchRecord` for the fail-closed type test.

    Satisfies the store's write Protocol (a content-addressed id + a deterministic
    ``to_dict``) but its payload cannot decode as a
    :class:`~quantforge.factorrisk.result.FactorRiskModel`, so referencing it exercises
    the engine's "resolved record is not a risk model" fail-closed guard (PO-3).
    """

    research_result_id: str

    def to_dict(self) -> dict[str, object]:
        return {"kind": "not-a-factor-risk-model", "id": self.research_result_id}
