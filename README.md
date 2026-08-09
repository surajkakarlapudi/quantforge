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
Universe research
    ↓
Fundamental panels
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
- Universe research (deterministic membership, construction, inspection, comparison, export)
- Point-in-time fundamental panels (period-series, vintage, cross-sectional matrix)
- Point-in-time market data (unadjusted daily OHLCV + first-class corporate actions, PIT-gated adjusted views)
- Full fact-to-source provenance
- Content-addressed versioning
- Offline/reproducible research
## Example

from quantforge import Company

apple = Company.resolve("AAPL")

filings = apple.filings()
facts = apple.facts()

# A universe: a deterministic, point-in-time collection of filers
from quantforge import Universe

universe = Universe.from_companies(["AAPL", "MSFT", "NVDA"])
universe.describe()          # a deterministic, serializable UniverseSummary
universe.compare(other)      # a UniverseComparison, diffed by canonical company_id
universe.to_records()        # dependency-free tabular export

# A fundamental panel: one metric over an explicit, content-addressed time axis
from quantforge.panel import PeriodAxis
from quantforge.xbrl.contexts import PeriodType

axis = PeriodAxis.annual("2018-12-31", "2023-12-31", period_type=PeriodType.INSTANT)
panel = apple.panel_as_of("current_ratio", axis, as_of)  # a PitPanel, one cell/period
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
| v0.5.0 | Universe research layer (management, construction, inspection, comparison, export) |
| v0.6.0 | Point-in-time fundamental panel (period-series, vintage, cross-sectional matrix) |
| v0.7.0 | Point-in-time market data layer (unadjusted OHLCV, first-class corporate actions, PIT-gated adjusted views, `PitPrice` / `RevisedPrice`) |
| Next | Portfolio / backtesting infrastructure |

## Status

QuantForge is an active research/infrastructure project.
Some components are provisional and explicitly versioned as such.
The project prioritizes correctness, reproducibility, and auditability
over breadth.
