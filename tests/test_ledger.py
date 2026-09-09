"""The ledger must detect any edit to the paper-trading record.

A paper log is only evidence if it cannot be quietly improved after the fact.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ballast.ledger import Ledger, LedgerError

SECRET = b"test-secret"


class TestTamperEvidence(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = Path(self.dir.name) / "ledger.jsonl"
        self.ledger = Ledger(self.path, SECRET)
        for i in range(4):
            self.ledger.append("decision", {"ticker": f"T{i}", "action": "HEDGE"})

    def tearDown(self):
        self.dir.cleanup()

    def _lines(self):
        return [json.loads(l) for l in self.path.read_text().splitlines() if l.strip()]

    def _rewrite(self, entries):
        self.path.write_text("\n".join(json.dumps(e) for e in entries) + "\n")

    def test_clean_chain_verifies(self):
        self.assertEqual(self.ledger.verify(), 4)

    def test_mutation_is_detected(self):
        entries = self._lines()
        entries[1]["body"]["action"] = "NO_HEDGE"      # rewrite a losing decision
        self._rewrite(entries)
        with self.assertRaises(LedgerError):
            self.ledger.verify()

    def test_deletion_is_detected(self):
        entries = self._lines()
        del entries[2]                                  # drop an inconvenient night
        self._rewrite(entries)
        with self.assertRaises(LedgerError):
            self.ledger.verify()

    def test_reorder_is_detected(self):
        entries = self._lines()
        entries[1], entries[2] = entries[2], entries[1]
        self._rewrite(entries)
        with self.assertRaises(LedgerError):
            self.ledger.verify()

    def test_signature_swap_is_detected(self):
        entries = self._lines()
        entries[1]["sig"] = entries[2]["sig"]
        self._rewrite(entries)
        with self.assertRaises(LedgerError):
            self.ledger.verify()

    def test_forged_append_without_the_secret_is_detected(self):
        entries = self._lines()
        forged = dict(entries[-1])
        forged["seq"] = len(entries)
        forged["prev"] = entries[-1]["hash"]
        forged["body"] = {"ticker": "FAKE", "action": "HEDGE"}
        entries.append(forged)
        self._rewrite(entries)
        with self.assertRaises(LedgerError):
            self.ledger.verify()

    def test_verification_needs_the_right_secret(self):
        with self.assertRaises(LedgerError):
            Ledger(self.path, b"wrong-secret").verify()


if __name__ == "__main__":
    unittest.main()
