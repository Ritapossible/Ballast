"""Render the whole site into a scratch directory, leaving docs/ untouched.

    python3 tools/build_preview.py /tmp/site

docs/ holds the DEPLOYED pages, and the chain verdict is baked into them at build
time, so a local rebuild carrying the development key publishes a false claim
about a real-key ledger - that reached the live site once, and `refuse_dev_build`
exists because of it. Previewing by building into docs/ and remembering not to
commit is the same trap with a human in the loop.

So this builds somewhere else. Static assets are copied first and the generated
pages written over them, which is also what the browser check needs: a complete
site tree built from the CURRENT source rather than from whatever was committed
before the last scheduled rebuild.
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ballast import config, docs_page, report


def build(out: Path) -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)
    shutil.copytree(report.OUT_DIR, out, dirs_exist_ok=True)
    os.environ.setdefault("BALLAST_DEV_SECRET", "1")
    with mock.patch.object(report, "OUT_DIR", out), \
         mock.patch.object(docs_page, "OUT", out / "docs.html"):
        pages = report.build()
        pages.append(docs_page.build())
    return pages


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    target = Path(sys.argv[1]).resolve()
    if target == report.OUT_DIR:
        raise SystemExit(f"refusing to build into {config.ROOT / 'docs'} - "
                         "that is the deployed site, not a preview")
    for p in build(target):
        print(f"wrote {p.relative_to(target)} ({p.stat().st_size:,} bytes)")
