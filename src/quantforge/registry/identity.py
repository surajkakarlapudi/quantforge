"""Deterministic filing and company identity.

Identity in the registry follows ``docs/data-model.md`` §11 exactly:

* ``company_id`` = ``cik:`` + zero-padded 10-digit CIK, e.g. ``cik:0000320193``.
* ``filing_id`` = ``accession:`` + the canonical accession number, e.g.
  ``accession:0000320193-23-000106``.

The guiding rule (§11): **an identifier must never depend on a mutable value**
— never a ticker, a company name, a reported figure, or a file path. Every
function here derives identity solely from SEC-assigned stable identifiers
(CIK, accession number), and is a pure, deterministic function of its input.

Accession canonical form is the **dashed** 18-digit representation SEC assigns
(``NNNNNNNNNN-NN-NNNNNN``), matching the ``filing_id`` in §11. The undashed
form used in EDGAR URL paths is a *rendering* for URLs, produced by the Phase 1
``endpoints`` module; it is never the identity. The original string as supplied
by SEC is preserved verbatim in provenance (see :mod:`quantforge.registry.model`).
"""

from __future__ import annotations

import re

from quantforge.registry.errors import AccessionFormatError
from quantforge.sec.endpoints import canonical_cik, cik10

__all__ = [
    "canonical_accession",
    "cik_from_company_id",
    "company_id",
    "filing_id",
]

# SEC accession numbers are 10 digits (filer id) - 2 digits (year) - 6 digits
# (sequence). We accept the canonical dashed form and the undashed 18-digit
# form (as it appears in URL paths), and canonicalize both to the dashed form.
# We do NOT accept anything else: identity must be exact, never guessed.
_DASHED = re.compile(r"^(\d{10})-(\d{2})-(\d{6})$")
_UNDASHED = re.compile(r"^(\d{10})(\d{2})(\d{6})$")


def canonical_accession(accession: str) -> str:
    """Canonicalize an accession number to its dashed ``NNNNNNNNNN-NN-NNNNNN``.

    Accepts either the dashed form or the 18-digit undashed form (used in
    EDGAR URL paths) and normalizes to the dashed form used as ``filing_id``.
    Surrounding whitespace is stripped. Any other shape raises
    :class:`AccessionFormatError` — the registry never invents or repairs an
    accession number.
    """
    if not isinstance(accession, str):
        raise AccessionFormatError(accession)
    value = accession.strip()
    dashed = _DASHED.match(value)
    if dashed is not None:
        return value
    undashed = _UNDASHED.match(value)
    if undashed is not None:
        filer, year, seq = undashed.groups()
        return f"{filer}-{year}-{seq}"
    raise AccessionFormatError(accession)


def company_id(cik: str | int) -> str:
    """Return the canonical ``company_id`` for a CIK (``cik:`` + 10-digit).

    Reuses the Phase 1 CIK canonicalization so the submissions API's
    zero-padded string and the companyfacts API's integer map to one identity
    (§11). The CIK identifies the *filer/registrant*; per the data model a
    single CIK is the stable filer across name, ticker, and reincorporation
    changes. We do not model a separate economic-company identity here.
    """
    return f"cik:{cik10(cik)}"


def filing_id(accession: str) -> str:
    """Return the canonical ``filing_id`` (``accession:`` + canonical accession)."""
    return f"accession:{canonical_accession(accession)}"


def cik_from_company_id(value: str) -> str:
    """Recover the bare-integer CIK string from a ``company_id``.

    Inverse of :func:`company_id` (modulo zero-padding). Raises ``ValueError``
    if the string is not a ``cik:``-prefixed identifier.
    """
    if not value.startswith("cik:"):
        raise ValueError(f"not a company_id: {value!r}")
    return canonical_cik(value[len("cik:") :])
