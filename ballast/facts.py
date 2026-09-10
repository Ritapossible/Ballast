"""Measured facts the public pages quote, with the date they were measured.

The universe counts were written into the page as literals and had already drifted
- 219 of 699 became 224 of 704 within two days of listings changing. A live product
quoting a stale number it has no way of noticing is a slow, silent failure, so the
figures live in a generated file instead, and the site renders whatever is in it.

Refresh with `python3 research/facts_study.py`. The nightly job refreshes it too,
so it cannot drift for longer than a day.
"""
from __future__ import annotations

import json
from pathlib import Path

from . import config

FACTS_PATH = config.ROOT / "docs" / "facts.json"

# Fallback if the file is missing: the site must still build offline. These are the
# values measured on the date shown and are superseded the moment facts.json exists.
DEFAULTS = {
    "measured_on": "2026-09-08",
    "rtokens_total": 699,
    "rtokens_hedgeable": 219,
    "hedge_cost_bp": 11.3,
    "exit_cost_bp": 20.0,
    "median_r2": 0.980,
    "median_tail_cut_pct": 88,
}


def load() -> dict:
    try:
        data = json.loads(FACTS_PATH.read_text())
    except (OSError, json.JSONDecodeError):
        return dict(DEFAULTS)
    merged = dict(DEFAULTS)
    merged.update({k: v for k, v in data.items() if v is not None})
    return merged


def save(values: dict) -> Path:
    FACTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    FACTS_PATH.write_text(json.dumps(values, indent=2, sort_keys=True) + "\n")
    return FACTS_PATH
