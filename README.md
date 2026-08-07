# QuantForge

> **Early-stage project.** This is a *foundational* release. It establishes the
> repository, packaging, and development-tooling foundation only. **No financial
> functionality is implemented yet.** See [ARCHITECTURE.md](ARCHITECTURE.md) for
> the intended design and the current status of each component.

QuantForge aims to be reproducible, point-in-time infrastructure for financial
research built on public data. The guiding idea is that financial research
should be **reproducible** and free of look-ahead bias: raw data is stored
immutably, transformations are deterministic, and every derived value can be
traced back to its source as it was known at a point in time.

## Status

| Area | Status |
| --- | --- |
| Repository & tooling foundation | ✅ Exists (this release) |
| Ingestion of public financial data | 🔜 Planned |
| Immutable raw data store | 🔜 Planned |
| Parsing / normalization | 🔜 Planned |
| Provenance tracking | 🔜 Planned |
| Point-in-time data layer | 🔜 Planned |
| Factors | 🔜 Planned |
| Backtesting | 🔜 Planned |

Nothing above marked "Planned" exists yet. The package currently exposes only a
version string.

## Requirements

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) for environment and dependency management

## Development setup

```bash
# Create the environment and install the package + dev tooling
uv sync

# Run the test suite
uv run pytest

# Lint and format
uv run ruff check .
uv run ruff format --check .

# Type-check
uv run mypy

# Install git hooks (optional but recommended)
uv run pre-commit install
```

## Project layout

```
src/quantforge/   # the package (src layout)
tests/             # test suite
docs/              # documentation
examples/          # runnable examples (empty for now)
benchmarks/        # performance benchmarks (empty for now)
scripts/           # developer/operational scripts (empty for now)
```

## Principles

QuantForge follows a small set of non-negotiable engineering principles —
correctness over convenience, immutable raw data, provenance, point-in-time
integrity, determinism, and reproducibility. See the
[Engineering Principles](ARCHITECTURE.md#engineering-principles) section of
`ARCHITECTURE.md`.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## Security

See [SECURITY.md](SECURITY.md) for how to report vulnerabilities.

## License

[MIT](LICENSE)
