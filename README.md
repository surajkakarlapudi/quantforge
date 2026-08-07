# QuantForge

> A deterministic, point-in-time financial research engine built from SEC filings.

QuantForge is an open-source quantitative finance infrastructure project for
researchers, developers, and students who need reproducible financial data
without survivorship bias, look-ahead bias, or opaque data transformations.

## What QuantForge Does

QuantForge turns SEC filings into a reproducible research pipeline:

SEC filings
    ↓
Canonical financial facts
    ↓
Point-in-time availability
    ↓
Financial statements
    ↓
Financial metrics
    ↓
Cross-sectional factors
    ↓
Quantitative research

### Core capabilities

- SEC filing acquisition and provenance
- XBRL fact extraction and canonicalization
- Point-in-time financial data
- PIT vs. revised data separation
- Financial statement assembly
- Deterministic financial metrics
- Cross-sectional factor research
- Full fact-to-source provenance
- Content-addressed versioning
- Offline/reproducible research
## Example

from quantforge import Company

apple = Company.resolve("AAPL")

filings = apple.filings()
facts = apple.facts()
## Design Principles

QuantForge is built around several principles:

- No look-ahead
- No fabricated financial data
- No silent data loss
- Explicit PIT/REVISED separation
- Deterministic computation
- Full provenance
- Versioned transformations
- Fail-closed behavior
- Read-only composition of lower layers
## Project Status

| Version | Capability |
|---|---|
| v0.1.0 | SEC acquisition, XBRL, canonical facts, PIT availability |
| v0.2.0 | Financial statements & public Company API |
| v0.3.0 | Financial metrics |
| v0.4.0 | Cross-sectional factors + QuantForge rebrand |
| Next | Research / portfolio infrastructure |

## Status

QuantForge is an active research/infrastructure project.
Some components are provisional and explicitly versioned as such.
The project prioritizes correctness, reproducibility, and auditability
over breadth.
