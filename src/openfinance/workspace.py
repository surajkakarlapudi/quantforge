"""The composition root that wires Phases 1-5 into one reusable context.

:class:`Workspace` holds the existing stores and façades — the Phase 1
:class:`~openfinance.sec.storage.ArtifactStore`, the Phase 2
:class:`~openfinance.registry.registry.FilingRegistry`, the Phase 4
:class:`~openfinance.canonical.store.CanonicalFactStore`, and the company
:class:`~openfinance.identity.resolve.CompanyResolver` — assembled from a single
data root. It creates **no** new storage and duplicates **no** logic; it only
constructs the components each phase already defines and hands them to the
:class:`~openfinance.company.Company` façade.

Directory layout under the data root (matches the phase-validation layout)::

    <root>/sec/          # Phase 1 content-addressed artifacts (authoritative)
    <root>/registry/     # Phase 2 derived filing registry
    <root>/canonical/    # Phase 4 derived canonical facts

Wall-clock, network, and secrets never enter identity here — the workspace is a
plain wiring object. A network client is attached only when a User-Agent is
configured, and it is used solely to fetch the official ticker mapping once (and
only if it is not already cached).
"""

from __future__ import annotations

import os
from pathlib import Path

from openfinance.canonical.store import CanonicalFactStore
from openfinance.identity.resolve import CompanyResolver
from openfinance.registry.registry import FilingRegistry
from openfinance.registry.store import RegistryStore
from openfinance.sec.client import SecClient
from openfinance.sec.config import ENV_STORAGE_DIR, SecConfig
from openfinance.sec.storage import ArtifactStore

__all__ = ["ENV_DATA_ROOT", "Workspace"]

#: Environment variable naming the OpenFinance data root. When unset, the
#: workspace falls back to the parent of the Phase 1 storage dir (so an existing
#: ``<x>/sec`` acquisition tree yields ``<x>`` as the root).
ENV_DATA_ROOT = "OPENFINANCE_DATA_ROOT"


class Workspace:
    """Wire the existing per-phase stores and façades from one data root."""

    def __init__(
        self,
        *,
        artifact_store: ArtifactStore,
        registry: FilingRegistry,
        canonical_store: CanonicalFactStore,
        resolver: CompanyResolver,
    ) -> None:
        self._artifacts = artifact_store
        self._registry = registry
        self._canonical = canonical_store
        self._resolver = resolver

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

        When ``root`` is omitted it is read from ``OPENFINANCE_DATA_ROOT``, or
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

        artifacts = ArtifactStore(sec_root)
        registry = FilingRegistry(
            RegistryStore(registry_root), artifact_store=artifacts
        )
        canonical = CanonicalFactStore(canonical_root)
        sec_client = client if client is not None else cls._maybe_client(config)
        resolver = CompanyResolver(artifacts, client=sec_client)
        return cls(
            artifact_store=artifacts,
            registry=registry,
            canonical_store=canonical,
            resolver=resolver,
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
        from openfinance.sec import build_client
        from openfinance.sec.errors import ConfigError

        try:
            cfg = config if config is not None else SecConfig.from_env()
        except ConfigError:
            return None
        try:
            return build_client(cfg)
        except ConfigError:
            return None
