# Contributing to OpenFinance

Thanks for your interest. OpenFinance is early-stage; the foundation is being
built deliberately, so contributions that respect the project's principles are
especially valuable.

## Development environment

OpenFinance standardizes on **Python 3.11+** and **[uv](https://docs.astral.sh/uv/)**.

```bash
# Install dependencies (creates .venv, installs package + dev group)
uv sync

# Install git hooks
uv run pre-commit install
```

Do not rely on globally installed packages; use the project environment managed
by uv.

## Before you open a pull request

Run the full local check suite:

```bash
uv run ruff check .          # lint
uv run ruff format --check . # formatting
uv run mypy                  # type checking
uv run pytest                # tests
```

All of the above should pass. Pre-commit runs the linting, formatting, and type
checks automatically on commit.

## Engineering principles

Contributions must uphold the project's engineering principles. Read the
[Engineering Principles](ARCHITECTURE.md#engineering-principles) section of
`ARCHITECTURE.md` before contributing. In particular:

- **No fabricated financial data.** Do not commit datasets, and do not add
  example data that could be mistaken for real market data.
- **No secrets in source control.** Use `.env` (git-ignored) for local secrets.
- **Determinism and provenance.** Transformations must be reproducible and
  traceable to their sources.
- **Tests for critical behavior.** Anything affecting correctness or
  point-in-time integrity must be tested.
- **Minimal dependencies.** Add a dependency only when it is genuinely needed,
  and justify it in the pull request.

## Commit and PR conventions

- Keep commits focused and messages descriptive.
- Describe *what* changed and *why*.
- Reference related issues where applicable.

## Reporting bugs and requesting features

Open an issue with enough detail to reproduce or understand the request. For
security issues, follow [SECURITY.md](SECURITY.md) instead of opening a public
issue.
