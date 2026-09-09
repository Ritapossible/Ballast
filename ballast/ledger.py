"""Append-only, tamper-evident decision ledger.

Every record carries the hash of the record before it, and each record is signed
with HMAC-SHA256. Mutating, deleting or reordering any entry breaks the chain and
`verify()` fails. This is what makes the paper-trading log evidence rather than
an assertion.

Written as JSON Lines so it stays greppable and diffable.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import json
from pathlib import Path

GENESIS = "0" * 64


class LedgerError(RuntimeError):
    pass


def _canonical(record: dict) -> str:
    return json.dumps(record, sort_keys=True, separators=(",", ":"), default=str)


class Ledger:
    def __init__(self, path: Path, secret: bytes):
        self.path = Path(path)
        self._secret = secret
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _entries(self) -> list[dict]:
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text().splitlines() if line.strip()]

    def head(self) -> str:
        entries = self._entries()
        return entries[-1]["hash"] if entries else GENESIS

    def append(self, kind: str, body: dict, now: dt.datetime | None = None) -> dict:
        now = now or dt.datetime.now(dt.timezone.utc)
        record = {
            "seq": len(self._entries()),
            "at": now.isoformat(),
            "kind": kind,
            "prev": self.head(),
            "body": body,
        }
        payload = _canonical(record)
        record["hash"] = hashlib.sha256(payload.encode()).hexdigest()
        record["sig"] = hmac.new(self._secret, payload.encode(), hashlib.sha256).hexdigest()
        with self.path.open("a") as fh:
            fh.write(json.dumps(record, default=str) + "\n")
        return record

    def verify(self) -> int:
        """Re-derive the whole chain. Returns the entry count; raises on any break."""
        prev = GENESIS
        for i, entry in enumerate(self._entries()):
            stated_hash = entry.pop("hash", None)
            stated_sig = entry.pop("sig", None)
            if entry.get("seq") != i:
                raise LedgerError(f"entry {i}: sequence is {entry.get('seq')}")
            if entry.get("prev") != prev:
                raise LedgerError(f"entry {i}: chain broken")
            payload = _canonical(entry)
            if hashlib.sha256(payload.encode()).hexdigest() != stated_hash:
                raise LedgerError(f"entry {i}: content does not match its hash")
            expected = hmac.new(self._secret, payload.encode(), hashlib.sha256).hexdigest()
            if not stated_sig or not hmac.compare_digest(expected, stated_sig):
                raise LedgerError(f"entry {i}: signature does not verify")
            prev = stated_hash
        return len(self._entries())

    def records(self, kind: str | None = None) -> list[dict]:
        return [e for e in self._entries() if kind is None or e["kind"] == kind]
