"""Tests for ``metric_id`` — the identity of one metric *request* (metrics.md §6.2).

``metric_id`` names the question (formula version, engine version, filer, period,
boundary), never the value. It must be deterministic and sensitive to every
component — so a PIT and a REVISED metric of the same formula/period never collide.
"""

from __future__ import annotations

from openfinance.metrics.identity import metric_id

_KW = {
    "formula_id": "sha256:formula",
    "metric_engine_version_id": "sha256:engine",
    "company_id": "cik:0000320193",
    "period_key": "instant\x00\x002023-09-30",
    "boundary_key": "pit:2023-11-05T21:30:00Z",
}


def test_is_deterministic() -> None:
    assert metric_id(**_KW) == metric_id(**_KW)


def test_is_sha256_prefixed() -> None:
    assert metric_id(**_KW).startswith("sha256:")


def test_boundary_distinguishes_pit_from_revised() -> None:
    pit = metric_id(**{**_KW, "boundary_key": "pit:2023-11-05T21:30:00Z"})
    rev = metric_id(**{**_KW, "boundary_key": "rev:sha256:dataset"})
    assert pit != rev


def test_each_component_is_load_bearing() -> None:
    base = metric_id(**_KW)
    for key in _KW:
        changed = metric_id(**{**_KW, key: _KW[key] + "-x"})
        assert changed != base, f"metric_id is insensitive to {key}"
