"""The public :class:`Company` façade — a thin, typed entry point.

``Company`` is the front door of the library::

    from quantforge import Company

    apple = Company.resolve("AAPL")
    for filing in apple.filings():
        print(filing.form, filing.filing_date)
    facts = apple.facts()

It is deliberately **thin**. It owns no business logic and no data model of its
own: it resolves a user-facing identifier to the canonical filer identity via the
:class:`~quantforge.identity.resolve.CompanyResolver`, then delegates every query
to the existing layers —

* :meth:`filings` → Phase 2 :class:`~quantforge.registry.registry.FilingRegistry`
* :meth:`facts`   → Phase 4 :class:`~quantforge.canonical.store.CanonicalFactStore`
* :meth:`metric_as_of` / :meth:`revised_metric`
  → Phase 7 :class:`~quantforge.metrics.engine.MetricEngine`
* :meth:`panel_as_of` / :meth:`vintage_as_of` / :meth:`revised_panel`
  → Phase 10 :class:`~quantforge.panel.engine.PanelEngine` (per-filer shapes only;
  the cross-sectional matrix stays engine-only, Decision D6)

so it can never diverge from the system of record. All identity flows through the
canonical ``company_id`` (data-model §11); the ticker/name are descriptive labels
only and never touch identity, storage, or provenance.

The metric API preserves the PIT/REVISED discipline at the front door (§11, §12):
there is **no** default-mode ``metric()`` accessor — the caller must name PIT
(:meth:`metric_as_of`, a timezone-aware ``as_of``) or REVISED
(:meth:`revised_metric`, a pinned ``DatasetVersion``), and the two return the two
distinct result types (invariants 27, 28).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from quantforge.availability.version import DatasetVersion
from quantforge.canonical.model import Fact
from quantforge.canonical.store import CanonicalFactStore
from quantforge.identity.model import CompanyIdentity
from quantforge.metrics.engine import MetricEngine
from quantforge.metrics.model import (
    MetricPeriod,
    PitMetricValue,
    RevisedMetricValue,
)
from quantforge.panel.axis import PeriodAxis
from quantforge.panel.derive import Derivation
from quantforge.panel.engine import PanelEngine
from quantforge.panel.model import PitPanel, RevisedPanel
from quantforge.registry.model import FilingRecord
from quantforge.registry.registry import FilingRegistry
from quantforge.workspace import Workspace

__all__ = ["Company"]


@dataclass(frozen=True, slots=True)
class Company:
    """A resolved filer, exposing high-level queries over the existing backend.

    Construct via :meth:`resolve` (the public path) or :meth:`from_identity`
    (when an identity is already in hand). The instance holds the resolved
    :class:`CompanyIdentity` and the two existing façades it delegates to; it
    stores nothing itself.
    """

    identity: CompanyIdentity
    _registry: FilingRegistry
    _canonical: CanonicalFactStore
    _metric_engine: MetricEngine
    _panel_engine: PanelEngine

    # -- construction --------------------------------------------------------

    @classmethod
    def resolve(
        cls,
        identifier: str,
        *,
        by: str | None = None,
        workspace: Workspace | None = None,
    ) -> Company:
        """Resolve ``identifier`` (ticker, CIK, or exact company name) to a company.

        By default a ticker like ``"AAPL"`` is resolved via the official SEC
        ticker mapping and an all-digit / ``CIK``-prefixed value is treated as a
        CIK. Pass ``by="cik"`` / ``"ticker"`` / ``"name"`` to force the mode.

        ``workspace`` supplies the wired Phase 1-4 stores; when omitted a default
        :class:`Workspace` is opened from the environment (``QUANTFORGE_DATA_ROOT``
        or the configured Phase 1 storage dir). Fails closed on an unknown or
        ambiguous symbol.
        """
        ws = workspace if workspace is not None else Workspace.open()
        identity = ws.resolver.resolve(identifier, by=by)
        return cls.from_identity(identity, workspace=ws)

    @classmethod
    def from_identity(
        cls, identity: CompanyIdentity, *, workspace: Workspace
    ) -> Company:
        """Build a company from an already-resolved identity + a workspace."""
        engine = workspace.metric_engine
        assert isinstance(engine, MetricEngine)  # the workspace builds exactly this
        panel_engine = workspace.panel_engine
        assert isinstance(panel_engine, PanelEngine)  # the workspace builds this
        return cls(
            identity=identity,
            _registry=workspace.registry,
            _canonical=workspace.canonical_store,
            _metric_engine=engine,
            _panel_engine=panel_engine,
        )

    # -- identity accessors --------------------------------------------------

    @property
    def company_id(self) -> str:
        """The canonical ``company_id`` (``cik:``+10-digit) used across phases."""
        return self.identity.company_id

    @property
    def cik(self) -> str:
        """The canonical bare-integer CIK string."""
        return self.identity.cik

    @property
    def ticker(self) -> str | None:
        """The primary ticker from the official mapping, if any."""
        return self.identity.ticker

    @property
    def name(self) -> str | None:
        """The company title from the official mapping, if any."""
        return self.identity.name

    # -- delegated queries ---------------------------------------------------

    def filings(self) -> list[FilingRecord]:
        """All of this filer's filings, from the Phase 2 registry.

        Delegates to :meth:`FilingRegistry.list_filings`; returns the derived
        :class:`FilingRecord` set sorted by canonical accession (empty if the
        registry has not been built for this filer). No registry logic is
        duplicated here.
        """
        return self._registry.list_filings(self.cik)

    def filings_by_form(self, form: str) -> list[FilingRecord]:
        """This filer's filings of an exact form (e.g. ``"10-K"``)."""
        return self._registry.filings_by_form(self.cik, form)

    def facts(self) -> list[Fact]:
        """All canonical facts for this filer, from the Phase 4 canonical store.

        Delegates to :meth:`CanonicalFactStore.read_company`; returns the
        immutable :class:`Fact` set sorted by ``fact_id`` (empty if none are
        stored). Canonicalization and querying are not reimplemented here — this
        is a read-only view over the existing derived store.
        """
        return self._canonical.read_company(self.company_id)

    # -- derived metrics (Phase 7) ------------------------------------------

    def metric_as_of(
        self, metric_key: str, period: MetricPeriod, as_of: datetime
    ) -> PitMetricValue:
        """The point-in-time metric for this filer at ``as_of`` (§11, §12).

        Delegates to :meth:`MetricEngine.metric_as_of`. ``as_of`` must be
        timezone-aware (a naive instant is rejected by the Phase 5 choke point,
        invariant 15). Returns a :class:`PitMetricValue`; an input not yet public at
        ``as_of`` yields a first-class ``UNDEFINED`` result, never an error.
        """
        return self._metric_engine.metric_as_of(metric_key, self.cik, period, as_of)

    def revised_metric(
        self, metric_key: str, period: MetricPeriod, dataset_version: DatasetVersion
    ) -> RevisedMetricValue:
        """The revised metric over a pinned ``dataset_version`` (§11, §12).

        Delegates to :meth:`MetricEngine.revised_metric`. Returns a
        :class:`RevisedMetricValue`, which is *not* interchangeable with a PIT metric
        (invariant 28). Pass :meth:`dataset_version` to obtain the snapshot.
        """
        return self._metric_engine.revised_metric(
            metric_key, self.cik, period, dataset_version
        )

    def dataset_version(self) -> DatasetVersion:
        """The reproducible snapshot pin for this filer's REVISED metrics (§8)."""
        return self._metric_engine.dataset_version_for(self.cik)

    # -- fundamental panels (Phase 10) --------------------------------------

    def panel_as_of(
        self,
        metric_key: str,
        axis: PeriodAxis,
        as_of: datetime,
        *,
        derivation: Derivation | None = None,
    ) -> PitPanel:
        """The point-in-time period-series for this filer at ``as_of`` (§2, D6).

        A thin delegation to :meth:`PanelEngine.panel_as_of` — one metric over the
        declared :class:`~quantforge.panel.axis.PeriodAxis`, every period evaluated at
        the same ``as_of`` (timezone-aware; a naive instant is rejected by the Phase 5
        choke point). An optional multi-period
        :class:`~quantforge.panel.derive.Derivation` applies over the series. Returns a
        :class:`~quantforge.panel.model.PitPanel`. The cross-sectional matrix spans
        filers and so stays engine-only (:meth:`PanelEngine.panel_across`).
        """
        return self._panel_engine.panel_as_of(
            metric_key, self.cik, axis, as_of, derivation=derivation
        )

    def vintage_as_of(
        self,
        metric_key: str,
        period: MetricPeriod,
        as_of_axis: list[datetime] | tuple[datetime, ...],
    ) -> PitPanel:
        """The vintage / knowledge-evolution panel for this filer+period (Phase 10 §2).

        A thin delegation to :meth:`PanelEngine.vintage_as_of`: one metric at one
        fiscal ``period`` across many ``as_of`` instants, making restatement effects
        first-class. PIT-only — REVISED has no ``as_of`` axis (§3.1). Returns a
        :class:`~quantforge.panel.model.PitPanel`.
        """
        return self._panel_engine.vintage_as_of(
            metric_key, self.cik, period, as_of_axis
        )

    def revised_panel(
        self,
        metric_key: str,
        axis: PeriodAxis,
        dataset_version: DatasetVersion | None = None,
        *,
        derivation: Derivation | None = None,
    ) -> RevisedPanel:
        """The revised period-series for this filer over a pinned snapshot (§2).

        A thin delegation to :meth:`PanelEngine.revised_panel`. Returns a
        :class:`~quantforge.panel.model.RevisedPanel`, which is *not* interchangeable
        with a :class:`~quantforge.panel.model.PitPanel` (invariant 28); call
        :meth:`RevisedPanel.reinterpret_as_pit` for an explicit, re-evaluating
        conversion. REVISED has no vintage shape (§3.1).
        """
        return self._panel_engine.revised_panel(
            metric_key, self.cik, axis, dataset_version, derivation=derivation
        )

    def __repr__(self) -> str:
        label = self.ticker or self.name or self.cik
        return f"Company({label!r}, cik={self.cik!r})"
