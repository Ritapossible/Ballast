"""The workflow's commit step, run against a real repository.

A run at 2026-11-28 03:09Z died on four merge conflicts seven minutes after
another run had pushed. Everything it conflicted on is GENERATED and carries a
run timestamp - requestTime in the order log, built_on in the crosscheck and the
probe - so two runs minutes apart can never agree on those bytes and never need
to. The step had no handling for it at all.

The bug lived in shell inside a YAML file, which no test here had ever executed.
These run the real script, extracted from the workflow, against a real git
remote with a real concurrent push.
"""
from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github/workflows/nightly.yml"


def commit_script() -> str:
    steps = yaml.safe_load(WORKFLOW.read_text())["jobs"]["run"]["steps"]
    return next(s["run"] for s in steps
                if s.get("name", "").startswith("Commit the ledger"))


def git(*args, cwd, check=True):
    return subprocess.run(["git", *args], cwd=cwd, check=check,
                          capture_output=True, text=True)


class TheCommitStepSurvivesAConcurrentRun(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.remote = root / "remote.git"
        subprocess.run(["git", "init", "--bare", "-b", "main", str(self.remote)],
                       check=True, capture_output=True)
        self.a, self.b = root / "a", root / "b"
        for who in (self.a, self.b):
            subprocess.run(["git", "clone", str(self.remote), str(who)],
                           check=True, capture_output=True)
            git("config", "user.email", "t@t", cwd=who)
            git("config", "user.name", "t", cwd=who)
        # A starting state both runners share.
        (self.a / "state").mkdir()
        (self.a / "docs").mkdir()
        (self.a / "state/ledger.jsonl").write_text('{"seq":0}\n')
        (self.a / "state/signal_probe.json").write_text('{"built_on":"first"}\n')
        # docs/ must exist in the tree: git does not track empty directories and
        # the step stages it by name.
        (self.a / "docs/index.html").write_text("<html>start</html>\n")
        (self.a / "README.md").write_text("start\n")
        git("add", "-A", cwd=self.a)
        git("commit", "-m", "base", cwd=self.a)
        git("push", "origin", "main", cwd=self.a)
        git("pull", "origin", "main", cwd=self.b)
        self.script = commit_script()

    def tearDown(self):
        self.tmp.cleanup()

    def run_step(self, cwd):
        path = Path(cwd) / "step.sh"
        path.write_text(self.script)
        return subprocess.run(["bash", "-e", str(path)], cwd=cwd,
                              capture_output=True, text=True)

    def test_a_generated_file_conflict_resolves_instead_of_failing(self):
        # The other runner publishes first.
        (self.a / "state/signal_probe.json").write_text('{"built_on":"A"}\n')
        git("commit", "-am", "A regenerated", cwd=self.a)
        git("push", "origin", "main", cwd=self.a)
        # This runner regenerated the same file with its own timestamp.
        (self.b / "state/signal_probe.json").write_text('{"built_on":"B"}\n')
        done = self.run_step(self.b)
        self.assertEqual(done.returncode, 0,
                         f"the step failed on a generated file:\n{done.stdout}\n{done.stderr}")
        self.assertNotIn("<<<<<<<", (self.b / "state/signal_probe.json").read_text(),
                         "conflict markers were committed")

    def test_a_real_ledger_conflict_is_refused_rather_than_guessed(self):
        (self.a / "state/ledger.jsonl").write_text('{"seq":0}\n{"seq":1,"by":"A"}\n')
        git("commit", "-am", "A appended", cwd=self.a)
        git("push", "origin", "main", cwd=self.a)
        (self.b / "state/ledger.jsonl").write_text('{"seq":0}\n{"seq":1,"by":"B"}\n')
        done = self.run_step(self.b)
        self.assertEqual(done.returncode, 1,
                         "two runs disagreeing about the chain must not be "
                         "auto-resolved")
        self.assertIn("ledger.jsonl conflicted", done.stdout + done.stderr)

    def test_an_uncontested_change_still_commits_and_pushes(self):
        (self.b / "state/signal_probe.json").write_text('{"built_on":"B"}\n')
        done = self.run_step(self.b)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("B", git("show", "origin/main:state/signal_probe.json",
                               cwd=self.b).stdout)

    def test_nothing_to_commit_is_not_a_failure(self):
        done = self.run_step(self.b)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("nothing changed", done.stdout)


if __name__ == "__main__":
    unittest.main()
