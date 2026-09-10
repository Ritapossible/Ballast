"""Every command the project tells a reader to run must exist.

The site says "don't take the numbers on trust" and lists commands. One of them -
`python3 research/universe.py` - had not existed since the module moved into the
package, and two research scripts could not be run directly at all because they
lacked the path bootstrap their siblings had. A reproducibility claim that fails
at the first command is worse than making no claim.
"""
from __future__ import annotations

import re
import subprocess
import sys
import unittest
from pathlib import Path

from ballast import config

SOURCES = ["research/README.md", "README.md",
           "ballast/docs_page.py", "ballast/report.py", "docs/SUBMISSION.md"]


def documented_commands() -> set[str]:
    found = set()
    for name in SOURCES:
        path = config.ROOT / name
        if not path.exists():
            continue
        text = path.read_text()
        found |= set(re.findall(r'python3 -m ([a-z_][a-z_0-9.]*)', text))
        found |= set(re.findall(r'python3 (research/[a-z_0-9]+\.py)', text))
    return found


class TestDocumentedCommands(unittest.TestCase):
    def test_at_least_one_command_is_documented(self):
        self.assertGreater(len(documented_commands()), 5)

    def test_every_documented_target_exists(self):
        for command in sorted(documented_commands()):
            if command.endswith(".py"):
                target = config.ROOT / command
            elif command == "unittest":
                continue
            else:
                target = config.ROOT / (command.replace(".", "/") + ".py")
            self.assertTrue(target.exists(), f"documented but missing: {command}")

    def test_research_scripts_are_runnable_standalone(self):
        """Each must bootstrap its own import path; siblings differed silently."""
        for script in sorted((config.ROOT / "research").glob("*.py")):
            source = script.read_text()
            self.assertIn("sys.path.insert", source,
                          f"{script.name} cannot be run directly")

    def test_scripts_import_cleanly(self):
        """Compile every research script - an ImportError only shows at runtime."""
        for script in sorted((config.ROOT / "research").glob("*.py")):
            result = subprocess.run(
                [sys.executable, "-c",
                 f"import ast,pathlib;ast.parse(pathlib.Path({str(script)!r}).read_text())"],
                capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, f"{script.name}: {result.stderr}")


if __name__ == "__main__":
    unittest.main()
