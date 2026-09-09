"""Paths and secrets. One place, so nothing else guesses."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "state"
BOOK_PATH = STATE / "book.json"
LEDGER_PATH = STATE / "ledger.jsonl"

DEV_SECRET = b"ballast-dev-secret-not-for-production"


def secret() -> bytes:
    """Mandate and ledger signing key.

    In paper mode a development default is acceptable and is reported as such;
    a live deployment must set BALLAST_SECRET or the signatures prove nothing.
    """
    raw = os.environ.get("BALLAST_SECRET")
    return raw.encode() if raw else DEV_SECRET


def using_dev_secret() -> bool:
    return not os.environ.get("BALLAST_SECRET")
