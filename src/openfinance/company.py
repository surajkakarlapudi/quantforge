"""The public :class:`Company` façade — a thin, typed entry point.

``Company`` is the front door of the library::

    from openfinance import Company

    apple = Company.resolve("AAPL")
    for filing in apple.filings():
        print(filing.form, filing.filing_date)
    facts = apple.facts()

It is deliberately **thin**. It owns no business logic and no data model of its
own: it resolves a user-facing identifier to the canonical filer identity via the
:class:`~openfinance.identity.resolve.CompanyResolver`, then delegates every query
to the existing layers —

* :meth:`filings` → Phase 2 :class:`~openfinance.registry.registry.FilingRegistry`
* :meth:`facts`   → Phase 4 :class:`~openfinance.canonical.store.CanonicalFactStore`

so it can never diverge from the system of record. All identity flows through the
canonical ``company_id`` (data-model §11); the ticker/name are descriptive labels
only and never touch identity, storage, or provenance.
"""

from __future__ import annotations

from dataclasses import dataclass

from openfinance.canonical.model import Fact
from openfinance.canonical.store import CanonicalFactStore
from openfinance.identity.model import CompanyIdentity
from openfinance.registry.model import FilingRecord
from openfinance.registry.registry import FilingRegistry
from openfinance.workspace import Workspace

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
        :class:`Workspace` is opened from the environment (``OPENFINANCE_DATA_ROOT``
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
        return cls(
            identity=identity,
            _registry=workspace.registry,
            _canonical=workspace.canonical_store,
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

    def __repr__(self) -> str:
        label = self.ticker or self.name or self.cik
        return f"Company({label!r}, cik={self.cik!r})"
