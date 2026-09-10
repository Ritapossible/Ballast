"""Paths and secrets. One place, so nothing else guesses."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "state"
BOOK_PATH = STATE / "book.json"
LEDGER_PATH = STATE / "ledger.jsonl"

DEV_SECRET = b"ballast-dev-secret-not-for-production"


class UnsignedError(RuntimeError):
    """No signing key, and the development fallback was not explicitly requested."""


def secret() -> bytes:
    """Mandate and ledger signing key.

    DEV_SECRET is a constant committed to a public repository, so anything signed
    with it can be forged by anyone who reads the source - the signature proves
    nothing. Falling back to it silently while the site advertises a
    "signed, tamper-evident" ledger is the security problem, not the fallback
    itself. So the fallback now has to be asked for: set BALLAST_DEV_SECRET=1.
    """
    raw = os.environ.get("BALLAST_SECRET")
    if raw:
        return raw.encode()
    if os.environ.get("BALLAST_DEV_SECRET") == "1":
        return DEV_SECRET
    raise UnsignedError(
        "BALLAST_SECRET is not set. The ledger and mandate signatures would be "
        "forgeable by anyone with the source. Set BALLAST_SECRET, or set "
        "BALLAST_DEV_SECRET=1 to accept an unverifiable development key.")


def using_dev_secret() -> bool:
    """True when signatures are unverifiable and must be labelled as such."""
    return not os.environ.get("BALLAST_SECRET")
