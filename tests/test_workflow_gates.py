"""A CI gate that does not run is worse than no gate, because it reads as one.

`tools/submission_counts.py --check` sat in ci.yml for weeks without ever
executing. Its `run:` was a plain scalar written across two lines, so YAML folded
the pair into one command and the second script became trailing argv for the
first, which ignored it and exited 0. The step was green the whole time. The
counts it guards had already drifted.

These tests read the workflow text rather than a parsed document, because the
defect is invisible once the parser has folded it away - and because CI installs
no YAML library.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

WORKFLOWS = Path(__file__).resolve().parent.parent / ".github" / "workflows"

#: `run:` carrying an inline value. Group 1 is the indent of the key itself,
#: group 2 the value - a block indicator (`|`, `>`, with optional chomping and
#: an explicit indent digit) or the first line of a plain scalar.
RUN = re.compile(r"^(\s*)(?:-\s+)?run:[ \t]+(.*)$")
BLOCK = re.compile(r"^[|>][+-]?\d?\s*(#.*)?$")


def _continuation(lines: list[str], start: int, indent: int) -> str | None:
    """The first line after `start` that YAML would fold into the scalar."""
    for line in lines[start + 1 :]:
        if not line.strip():
            continue
        if line.lstrip().startswith("#"):
            return None
        return line if len(line) - len(line.lstrip()) > indent else None
    return None


class EveryGateInTheWorkflowsActuallyRuns(unittest.TestCase):
    def _files(self) -> list[Path]:
        files = sorted(WORKFLOWS.glob("*.yml")) + sorted(WORKFLOWS.glob("*.yaml"))
        self.assertTrue(files, f"no workflows found under {WORKFLOWS}")
        return files

    def test_no_run_step_folds_its_commands_onto_one_line(self):
        for path in self._files():
            lines = path.read_text().splitlines()
            for i, line in enumerate(lines):
                m = RUN.match(line)
                if not m or BLOCK.match(m.group(2)):
                    continue
                nxt = _continuation(lines, i, len(m.group(1)))
                self.assertIsNone(
                    nxt,
                    f"{path.name}:{i + 1} runs a plain scalar across lines, so YAML "
                    f"joins it with {nxt.strip() if nxt else ''!r} into a single "
                    f"command. Use `run: |`.",
                )

    def test_the_submission_counts_check_is_one_of_them(self):
        """The specific gate this file was written for."""
        text = (WORKFLOWS / "ci.yml").read_text()
        self.assertIn("python tools/submission_counts.py --check", text)
        for line in text.splitlines():
            if "submission_counts.py --check" in line and "run:" in line:
                self.fail(f"gate shares a `run:` line with something else: {line!r}")


if __name__ == "__main__":
    unittest.main()
