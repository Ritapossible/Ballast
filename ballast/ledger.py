"""Append-only, tamper-evident decision ledger.

Every record carries the hash of the record before it, and each record is signed
with HMAC-SHA256. Mutating, deleting or reordering any entry breaks the chain and
`verify()` fails. This is what makes the paper-trading log evidence rather than
an assertion.

Written as JSON Lines so it stays greppable and diffable.
"""
from __future__ import annotations

import datetime as dt
import fcntl
import hashlib
import hmac
import json
import os
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

    def _last_line(self, fh) -> str | None:
        """Read only the final line.

        Appending used to parse the entire file twice - once for the sequence
        number and once for the previous hash - which made a night of writes
        quadratic in the size of the record it was extending.
        """
        fh.seek(0, os.SEEK_END)
        end = fh.tell()
        if end == 0:
            return None
        size, block = 0, 1024
        while size < end:
            size = min(size + block, end)
            fh.seek(end - size)
            chunk = fh.read(size)
            lines = [l for l in chunk.split(b"\n") if l.strip()]
            if len(lines) >= 2 or size == end:
                return lines[-1].decode() if lines else None
        return None

    def head(self) -> str:
        if not self.path.exists():
            return GENESIS
        with self.path.open("rb") as fh:
            line = self._last_line(fh)
        return json.loads(line)["hash"] if line else GENESIS

    def append(self, kind: str, body: dict, now: dt.datetime | None = None) -> dict:
        """Append one record under an exclusive lock.

        Without the lock two writers - a scheduled run and a manual one - can read
        the same head, both append, and leave a chain with a duplicated sequence
        number that no longer verifies.
        """
        now = now or dt.datetime.now(dt.timezone.utc)
        self.path.touch(exist_ok=True)
        with self.path.open("r+b") as fh:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
            try:
                last = self._last_line(fh)
                if last:
                    previous = json.loads(last)
                    seq, prev_hash = previous["seq"] + 1, previous["hash"]
                else:
                    seq, prev_hash = 0, GENESIS

                record = {"seq": seq, "at": now.isoformat(), "kind": kind,
                          "prev": prev_hash, "body": body}
                payload = _canonical(record)
                record["hash"] = hashlib.sha256(payload.encode()).hexdigest()
                record["sig"] = hmac.new(self._secret, payload.encode(),
                                         hashlib.sha256).hexdigest()
                fh.seek(0, os.SEEK_END)
                fh.write((json.dumps(record, default=str) + "\n").encode())
                fh.flush()
                os.fsync(fh.fileno())
            finally:
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        return record

    def verify(self) -> int:
        """Re-derive the whole chain. Returns the entry count; raises on any break."""
        prev, count = GENESIS, 0
        entries = self._entries()
        count = len(entries)
        for i, entry in enumerate(entries):
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
        return count

    def records(self, kind: str | None = None) -> list[dict]:
        return [e for e in self._entries() if kind is None or e["kind"] == kind]

    def signed_by_other_key(self) -> bool:
        """True if the chain was written with a different signing key.

        A chain cannot span a key rotation: verification walks from entry zero, so
        one entry signed with the old key breaks every later one. Detecting this
        before appending turns a permanently unverifiable ledger into a clear
        instruction to rotate.
        """
        entries = self._entries()
        if not entries:
            return False
        first = entries[0]
        stated = first.pop("sig", None)
        first.pop("hash", None)
        expected = hmac.new(self._secret, _canonical(first).encode(),
                            hashlib.sha256).hexdigest()
        return not (stated and hmac.compare_digest(expected, stated))

    def rotate(self, archive: Path, reason: str) -> Path:
        """Retire a chain signed with a superseded key and start a fresh one.

        The old file is kept rather than deleted: it is still a true record of what
        was decided, it is preserved in git history regardless, and quietly
        discarding it would be the sort of thing this ledger exists to prevent.
        """
        archive.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            archive.write_text(self.path.read_text())
            self.path.unlink()
        self.append("chain_start", {
            "reason": reason,
            "archived_to": archive.name,
            "note": "the archived chain was signed with a key that is public in "
                    "this repository, so its signatures were never evidence",
        })
        return archive
