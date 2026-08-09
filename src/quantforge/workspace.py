"""The composition root that wires Phases 1-5 into one reusable context.

:class:`Workspace` holds the existing stores and façades — the Phase 1
:class:`~quantforge.sec.storage.ArtifactStore`, the Phase 2
:class:`~quantforge.registry.registry.FilingRegistry`, the Phase 4
:class:`~quantforge.canonical.store.CanonicalFactStore`, and the company
:class:`~quantforge.identity.resolve.CompanyResolver` — assembled from a single
data root. It creates **no** new storage and duplicates **no** logic; it only
constructs the components each phase already defines and hands them to the
:class:`~quantforge.company.Company` façade.

Directory layout under the data root (matches the phase-validation layout)::

    <root>/sec/          # Phase 1 content-addressed artifacts (authoritative)
    <root>/registry/     # Phase 2 derived filing registry
    <root>/canonical/    # Phase 4 derived canonical facts
    <root>/availability/ # Phase 5 derived availability (wired here, not new code)

Wall-clock, network, and secrets never enter identity here — the workspace is a
plain wiring object. A network client is attached only when a User-Agent is
configured, and it is used solely to fetch the official ticker mapping once (and
only if it is not already cached).

Phase 7 extends the workspace **additively**: it wires the already-existing Phase 5
:class:`~quantforge.availability.store.AvailabilityStore` /
:class:`~quantforge.availability.ingest.AvailabilityIngestor` under
``<root>/availability/`` and lazily builds a
:class:`~quantforge.metrics.engine.MetricEngine`. No prior store is edited and no
fact is rewritten — the derived-metrics path composes on top of the existing chain.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

from quantforge.availability.ingest import AvailabilityIngestor
from quantforge.availability.store import AvailabilityStore
from quantforge.canonical.store import CanonicalFactStore
from quantforge.identity.resolve import CompanyResolver
from quantforge.registry.registry import FilingRegistry
from quantforge.registry.store import RegistryStore
from quantforge.sec.client import SecClient
from quantforge.sec.config import ENV_STORAGE_DIR, SecConfig
from quantforge.sec.storage import ArtifactStore

if TYPE_CHECKING:
    from quantforge.factors.store import ResearchResultStore

__all__ = ["ENV_DATA_ROOT", "Workspace"]

#: Environment variable naming the QuantForge data root. When unset, the
#: workspace falls back to the parent of the Phase 1 storage dir (so an existing
#: ``<x>/sec`` acquisition tree yields ``<x>`` as the root).
ENV_DATA_ROOT = "QUANTFORGE_DATA_ROOT"


class Workspace:
    """Wire the existing per-phase stores and façades from one data root."""

    def __init__(
        self,
        *,
        artifact_store: ArtifactStore,
        registry: FilingRegistry,
        canonical_store: CanonicalFactStore,
        resolver: CompanyResolver,
        availability_store: AvailabilityStore,
        research_result_store: ResearchResultStore | None = None,
    ) -> None:
        self._artifacts = artifact_store
        self._registry = registry
        self._canonical = canonical_store
        self._resolver = resolver
        self._availability_store = availability_store
        self._research_result_store = research_result_store
        # The Phase 5 façade and the Phase 7/8 engines are built lazily and cached,
        # so a workspace that never touches metrics or factors pays nothing for them
        # (and there is no import cycle at module load — the engines import
        # :class:`Workspace`, so they are imported on first use, not here).
        self._availability_ingestor: AvailabilityIngestor | None = None
        self._metric_engine: object | None = None
        self._factor_engine: object | None = None
        self._panel_engine: object | None = None

    @property
    def artifact_store(self) -> ArtifactStore:
        return self._artifacts

    @property
    def registry(self) -> FilingRegistry:
        return self._registry

    @property
    def canonical_store(self) -> CanonicalFactStore:
        return self._canonical

    @property
    def resolver(self) -> CompanyResolver:
        return self._resolver

    @property
    def availability_store(self) -> AvailabilityStore:
        return self._availability_store

    @property
    def availability_ingestor(self) -> AvailabilityIngestor:
        """The Phase 5 availability façade over this workspace's wired stores.

        Built once and cached. It derives availability offline and constructs the
        point-in-time resolver the metric engine needs — reusing the existing Phase
        5 component, never a new store.
        """
        if self._availability_ingestor is None:
            self._availability_ingestor = AvailabilityIngestor(
                self._registry,
                self._availability_store,
                artifact_store=self._artifacts,
                canonical_store=self._canonical,
            )
        return self._availability_ingestor

    @property
    def metric_engine(self) -> object:
        """The Phase 7 :class:`~quantforge.metrics.engine.MetricEngine` (lazy).

        Imported on first use to avoid a module-load import cycle (the engine
        imports :class:`Workspace`). Cached for reuse.
        """
        if self._metric_engine is None:
            from quantforge.metrics.engine import MetricEngine

            self._metric_engine = MetricEngine(self)
        return self._metric_engine

    @property
    def research_result_store(self) -> ResearchResultStore:
        """The Phase 8 :class:`ResearchResultStore` sidecar under ``<root>/research/``.

        Built once and cached, mirroring the other derived stores. It sits beside
        the Phase 5 availability tree (``availability_store.root`` is
        ``<root>/availability``, so its parent is the data root), so no new root has
        to be threaded through construction. A caller may inject one explicitly.
        """
        if self._research_result_store is None:
            from quantforge.factors.store import ResearchResultStore

            self._research_result_store = ResearchResultStore(
                self._availability_store.root.parent
            )
        return self._research_result_store

    @property
    def factor_engine(self) -> object:
        """The Phase 8 :class:`~quantforge.factors.engine.FactorEngine` (lazy).

        Imported on first use to avoid a module-load import cycle (the engine
        imports :class:`Workspace`). Cached for reuse.
        """
        if self._factor_engine is None:
            from quantforge.factors.engine import FactorEngine

            self._factor_engine = FactorEngine(self)
        return self._factor_engine

    @property
    def panel_engine(self) -> object:
        """The Phase 10 :class:`~quantforge.panel.engine.PanelEngine` (lazy).

        Imported on first use to avoid a module-load import cycle (the engine
        imports :class:`Workspace`). Cached for reuse; it reuses this workspace's
        Phase 7 metric engine, Phase 8 factor engine, and research sidecar rather
        than building any new store.
        """
        if self._panel_engine is None:
            from quantforge.panel.engine import PanelEngine

            self._panel_engine = PanelEngine(self)
        return self._panel_engine

    # -- construction --------------------------------------------------------

    @classmethod
    def open(
        cls,
        root: str | os.PathLike[str] | None = None,
        *,
        config: SecConfig | None = None,
        client: SecClient | None = None,
    ) -> Workspace:
        """Assemble a workspace from a data ``root`` (or the environment).

        When ``root`` is omitted it is read from ``QUANTFORGE_DATA_ROOT``, or
        else derived as the parent of the configured Phase 1 storage dir. A
        network :class:`SecClient` is attached automatically when a User-Agent is
        configured (used only to fetch the ticker mapping once, cache-first); if
        none is available the workspace is fully offline and ticker/name
        resolution requires an already-cached mapping.
        """
        data_root = cls._resolve_root(root, config)
        sec_root = data_root / "sec"
        registry_root = data_root / "registry"
        canonical_root = data_root / "canonical"
        availability_root = data_root / "availability"

        artifacts = ArtifactStore(sec_root)
        registry = FilingRegistry(
            RegistryStore(registry_root), artifact_store=artifacts
        )
        canonical = CanonicalFactStore(canonical_root)
        availability = AvailabilityStore(availability_root)
        sec_client = client if client is not None else cls._maybe_client(config)
        resolver = CompanyResolver(artifacts, client=sec_client)
        return cls(
            artifact_store=artifacts,
            registry=registry,
            canonical_store=canonical,
            resolver=resolver,
            availability_store=availability,
        )

    @staticmethod
    def _resolve_root(
        root: str | os.PathLike[str] | None, config: SecConfig | None
    ) -> Path:
        if root is not None:
            return Path(root)
        env_root = os.environ.get(ENV_DATA_ROOT)
        if env_root:
            return Path(env_root)
        # Fall back to the parent of the Phase 1 storage dir, so a workspace
        # lines up with an already-populated acquisition tree.
        storage_dir = (
            config.storage_dir
            if config is not None
            else os.environ.get(ENV_STORAGE_DIR, "./data/sec")
        )
        return Path(storage_dir).parent

    @staticmethod
    def _maybe_client(config: SecConfig | None) -> SecClient | None:
        """Build a network client only if a valid config is available.

        A missing/invalid User-Agent means we cannot lawfully call SEC, so we
        stay offline rather than fail construction — ticker/name resolution then
        needs an already-cached mapping, and CIK resolution still works.
        """
        from quantforge.sec import build_client
        from quantforge.sec.errors import ConfigError

        try:
            cfg = config if config is not None else SecConfig.from_env()
        except ConfigError:
            return None
        try:
            return build_client(cfg)
        except ConfigError:
            return None
