# QuantForge Documentation

QuantForge is an early-stage project. This documentation is foundational and
will expand as functionality is implemented.

## Contents

- [Architecture](../ARCHITECTURE.md) — intended high-level design and the
  current status of each component.
- [SEC Acquisition Layer](sec-acquisition.md) — Phase 1: retrieving and
  preserving raw SEC EDGAR source material.
- [Filing Registry](filing-registry.md) — Phase 2: the deterministic,
  provenance-tracked registry of SEC filings derived from acquisition artifacts.
- [Raw XBRL Ingestion](xbrl-ingestion.md) — Phase 3: parsing SEC XBRL instance
  artifacts into immutable, fully-provenanced, loss-preserving raw facts.
- [Canonicalization](canonicalization.md) — Phase 4: transforming raw facts into
  deterministic, structured canonical financial observations with complete
  lineage back to the raw source.
- [Public Availability & Point-in-Time](point-in-time.md) — Phase 5: deriving when
  each filing became public under a versioned policy, and serving point-in-time
  (PIT) and revised knowledge-state queries that are impossible to confuse.
- [Company Identity & Public API](company-api.md) — the `from quantforge import
  Company` front door: resolving tickers/CIKs/names to the canonical filer
  identity via the official SEC mapping, then delegating to the existing layers.
- [Financial Metrics & Research Layer](metrics.md) — Phase 7: deterministic,
  fail-closed derived metrics (ratios and arithmetic combinations) computed on
  demand over the point-in-time knowledge state, versioned and fully provenanced,
  served as distinct PIT and revised result types.
- [Engineering Principles](../ARCHITECTURE.md#engineering-principles) — the
  non-negotiable principles guiding the project.
- [Contributing](../CONTRIBUTING.md) — how to set up a development environment
  and contribute.
- [Security](../SECURITY.md) — how to report vulnerabilities.

## Status

No financial functionality is implemented yet. The current release establishes
the repository, packaging, and development-tooling foundation only.
