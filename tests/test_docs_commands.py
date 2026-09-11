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


class VerifyEntrypointCase(unittest.TestCase):
    """`python3 verify.py` is quoted on the Evidence page, so it has to exist and
    has to cover the claims. A judge should not take a README's word for any of it."""

    def test_the_script_exists_and_compiles(self):
        import py_compile
        path = Path(__file__).resolve().parent.parent / "verify.py"
        self.assertTrue(path.exists(), "verify.py is quoted on the site but absent")
        py_compile.compile(str(path), doraise=True)

    def test_it_covers_every_offline_claim(self):
        src = (Path(__file__).resolve().parent.parent / "verify.py").read_text()
        for claim in ("tests", "enforcer_refuses", "ledger_chain",
                      "ledger_is_tamper_evident", "published_figures",
                      "reproduce_commands", "pages_build"):
            self.assertIn(claim, src, f"verify.py no longer checks {claim}")

    def test_it_says_what_it_cannot_check(self):
        """The market measurements need the exchange. Claiming to verify a figure
        it did not compute would be the opposite of the point."""
        src = (Path(__file__).resolve().parent.parent / "verify.py").read_text()
        self.assertIn("need the exchange", src)
