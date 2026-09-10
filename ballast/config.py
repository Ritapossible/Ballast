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


DEV_BUILD_OVERRIDE = "BALLAST_ALLOW_DEV_BUILD"


def refuse_dev_build() -> None:
    """Refuse to generate public pages without the real signing key.

    The site is static: verification runs when the pages are built, and the
    result is baked into the HTML as a fixed string. So a rebuild carrying the
    development key, run against a ledger the scheduled job signed with the real
    one, publishes "CHAIN BROKEN" - a correct verification of the wrong key,
    rendered as a claim about the ledger. That is exactly how the live site broke
    on 2026-09-10, after a local rebuild followed a scheduled run.

    Only the holder of the key that signed the ledger may write pages that make a
    claim about it. Set BALLAST_ALLOW_DEV_BUILD=1 to preview locally, knowing the
    output must not be committed. The builders' build() functions are left
    unguarded so the tests can still render pages into a temporary directory.
    """
    if not using_dev_secret() or os.environ.get(DEV_BUILD_OVERRIDE) == "1":
        return
    raise UnsignedError(
        "refusing to build the public pages without BALLAST_SECRET. The chain "
        "status is baked into the HTML at build time, so a development-key build "
        "would publish a false verdict about a real-key ledger. Set "
        f"{DEV_BUILD_OVERRIDE}=1 for a local preview that must not be committed.")
