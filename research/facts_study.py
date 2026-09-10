"""Re-measure the facts the public pages quote, and write docs/facts.json.

    python3 research/facts_study.py
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ballast import costs, facts
from ballast.universe import hedgeable_pairs, unhedgeable_rtokens


def run() -> None:
    hedgeable = hedgeable_pairs()
    unhedgeable = unhedgeable_rtokens()
    current = facts.load()

    values = dict(current)
    values.update({
        "measured_on": dt.date.today().isoformat(),
        "rtokens_hedgeable": len(hedgeable),
        "rtokens_total": len(hedgeable) + len(unhedgeable),
        "hedge_cost_bp": round(costs.HEDGE_COST_BP, 1),
        "exit_cost_bp": round(costs.EXIT_COST_BP, 1),
    })

    for key in ("rtokens_hedgeable", "rtokens_total"):
        if current.get(key) != values[key]:
            print(f"  drift: {key} {current.get(key)} -> {values[key]}")

    path = facts.save(values)
    print(f"\nwrote {path}")
    for k, v in sorted(values.items()):
        print(f"  {k:22s} {v}")


if __name__ == "__main__":
    run()
