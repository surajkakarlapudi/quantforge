"""SEC EDGAR URL construction and CIK canonicalization.

Pure functions only — no I/O. Kept separate from the client so the URL scheme
is testable in isolation and documented in one place.

Two host families are used:

* ``data.sec.gov`` — the JSON APIs (submissions, companyfacts). Lenient about
  User-Agent.
* ``www.sec.gov`` — the Archives (filing index + documents). Returns ``403``
  without an email-format User-Agent.
"""

from __future__ import annotations

__all__ = [
    "canonical_cik",
    "cik10",
    "company_facts_url",
    "company_tickers_url",
    "filing_directory_url",
    "filing_document_url",
    "filing_index_url",
    "submissions_page_url",
    "submissions_url",
]

_DATA_HOST = "https://data.sec.gov"
_WWW_HOST = "https://www.sec.gov"


def canonical_cik(cik: str | int) -> str:
    """Normalize a CIK to its canonical bare-integer string form.

    SEC is inconsistent: submissions embeds a zero-padded ``"0000320193"`` while
    companyfacts uses the integer ``320193``. We canonicalize to the bare
    integer string so a company has one identity regardless of source.
    """
    if isinstance(cik, int):
        value = cik
    else:
        stripped = cik.strip()
        if stripped.upper().startswith("CIK"):
            stripped = stripped[3:]
        if not stripped.isdigit():
            raise ValueError(f"not a valid CIK: {cik!r}")
        value = int(stripped)
    if value < 0:
        raise ValueError(f"CIK must be non-negative: {cik!r}")
    return str(value)


def cik10(cik: str | int) -> str:
    """Return the 10-digit zero-padded CIK used in EDGAR URL paths."""
    return canonical_cik(cik).zfill(10)


def submissions_url(cik: str | int) -> str:
    """Primary submissions endpoint (contains ``filings.recent``)."""
    return f"{_DATA_HOST}/submissions/CIK{cik10(cik)}.json"


def submissions_page_url(page_filename: str) -> str:
    """URL for an overflow submissions page named in ``filings.files``.

    The primary submissions JSON lists older filings on additional pages under
    ``filings.files[*].name`` (e.g. ``CIK0000019617-submissions-001.json``).
    Following these is mandatory: the first response is *not* the complete
    filing history for prolific filers.
    """
    return f"{_DATA_HOST}/submissions/{page_filename}"


def company_facts_url(cik: str | int) -> str:
    """CompanyFacts (consolidated XBRL) endpoint."""
    return f"{_DATA_HOST}/api/xbrl/companyfacts/CIK{cik10(cik)}.json"


def company_tickers_url() -> str:
    """The official SEC ticker → CIK mapping (``company_tickers.json``).

    A single JSON document listing every EDGAR filer with an assigned ticker,
    mapping ticker and company title to CIK. It is the authoritative source for
    ticker/name → CIK resolution (recon confirmed no per-issuer lookup exists);
    we retrieve it once and cache it via the content-addressed store rather than
    hardcode any ticker or CIK. Served from ``www.sec.gov`` (not the JSON API
    host), so it requires the email-format User-Agent.
    """
    return f"{_WWW_HOST}/files/company_tickers.json"


def _accession_nodashes(accession: str) -> str:
    return accession.replace("-", "")


def filing_directory_url(cik: str | int, accession: str) -> str:
    """Base directory URL for a filing's package."""
    bare = canonical_cik(cik)
    return f"{_WWW_HOST}/Archives/edgar/data/{bare}/{_accession_nodashes(accession)}"


def filing_index_url(cik: str | int, accession: str) -> str:
    """The ``index.json`` describing every file in a filing package."""
    return f"{filing_directory_url(cik, accession)}/index.json"


def filing_document_url(cik: str | int, accession: str, filename: str) -> str:
    """URL for a single named document inside a filing package."""
    return f"{filing_directory_url(cik, accession)}/{filename}"
