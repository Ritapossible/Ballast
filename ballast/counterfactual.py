"""Did the model ever change the rule's answer?

Track 2 asks whether the LLM is a decision-maker or decoration. The honest way to
answer is to put its call beside the call the deterministic calendar rule would
have made on the same night, for every decision on the chain, and count the
disagreements. If the model never moves a NO_HEDGE to a HEDGE, it is decoration
and the record says so.

The comparison is computable because the calendar branch of `policy.decide` is a
pure function of one bit: is a report scheduled inside tonight's window. No market
data, no sigma - the volatility gate is off (RESEARCH.md §5), so a night with
nothing on the calendar is NO_HEDGE whatever the tape did. That bit is what
`night.calendar_risk` returns, and it is re-derivable after the fact.

Three things keep this from being a story told over the record.

THE RULE IS CALLED, NOT REIMPLEMENTED. The counterfactual action comes out of
`policy.decide` with `model_judgment=None`, the same function the nightly run uses.
If the volatility gate is ever turned back on, the calendar branch stops being
decidable from the calendar alone and this module returns None rather than a
plausible-looking guess.

THE DERIVATION IS CHECKED AGAINST THE LEDGER. On a night the reader abstained the
recorded decision IS the calendar's, so every `decided_by == "rule"` row is a test
of the re-derivation. The count of matches, and every mismatch, is published in the
payload and on the page. It is not asserted to work; it is shown working.

THE BIAS RUNS AGAINST THE HEADLINE. Nasdaq populates its release-time flag for
upcoming dates and degrades it to `time-not-supplied` for past ones, and
`scheduled_in_window` passes an unsupplied flag through both gates. So a
re-derivation can only ever flag MORE nights than the live run saw, never fewer -
which can only shrink the count of "calendar said no, model said hedge". The
flip count is a floor.

Rows are pinned on first derivation. Re-running must not silently rewrite what an
earlier build published because a public feed moved underneath it; an existing row
is only replaced by a calendar call the nightly run recorded at decision time,
which is better evidence than any re-derivation.

    python -m ballast.counterfactual      # -> state/counterfactual.json
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from . import config
from .earnings import SELECTOR_BUG_SESSIONS
from .ledger import Ledger
from .night import calendar_call
from .policy import DEFAULT_POLICY, PolicyConfig

OUT = config.STATE / "counterfactual.json"


def _path(given: Path | None) -> Path:
    """The index path, resolved when it is used rather than at import.

    `config.STATE` is what the tests redirect to a temporary directory. Binding the
    path at import would leave the page builders reading the repository's real
    index during a test that thought it had an empty ledger - a page asserting
    things the throwaway ledger never contained.
    """
    return given or (config.STATE / OUT.name)


def calendar_action(ticker: str, session: dt.date,
                    cfg: PolicyConfig | None = None) -> tuple[str | None, str | None]:
    """(action, flag) the calendar rule alone would have produced for this night.

    `night.calendar_call` is the one implementation, so this can never drift from
    what the nightly run records. Returns (None, None) when the rule is no longer
    decidable from the calendar alone - see the module docstring.
    """
    call = calendar_call(ticker, session, cfg)
    return call["action"], call["flag"]


def _key(row: dict) -> str:
    return f"{row.get('session', '')}|{row.get('ticker', '')}"


def _settled_index(ledger: Ledger) -> dict[str, dict]:
    out = {}
    for entry in ledger.records("settlement"):
        body = entry["body"]
        for row in body.get("rows", []):
            out[f"{body.get('session', '')}|{row.get('ticker', '')}"] = row
    return out


def _ledger() -> Ledger:
    """Reading the record is not a claim about it, so no signing key is required."""
    try:
        return Ledger(config.LEDGER_PATH, config.secret())
    except config.UnsignedError:
        return Ledger(config.LEDGER_PATH, config.DEV_SECRET)


def build(out: Path | None = None) -> Path:
    path = _path(out)
    pinned: dict[str, dict] = {}
    if path.exists():
        pinned = {_key(r): r for r in json.loads(path.read_text()).get("rows", [])}

    ledger = _ledger()
    settled = _settled_index(ledger)
    rows, mismatches = [], []

    for entry in ledger.records("decision"):
        body = entry["body"]
        session, ticker = body.get("session"), body.get("ticker")
        if not session or not ticker:
            continue
        decided_by = (body.get("inputs") or {}).get("decided_by")
        if decided_by == "none":
            continue                       # no decision was taken; nothing to compare

        # A calendar call the nightly run recorded at decision time beats both a
        # re-derivation and anything an earlier build pinned.
        recorded = body.get("calendar") or {}
        if recorded.get("action"):
            calendar, flag, source = recorded["action"], recorded.get("flag"), "recorded"
        elif (prior := pinned.get(f"{session}|{ticker}")) and prior.get("calendar"):
            calendar, flag, source = prior["calendar"], prior.get("flag"), prior["source"]
        else:
            calendar, flag = calendar_action(ticker, dt.date.fromisoformat(session))
            source = "derived"
        if calendar is None:
            continue

        action = body.get("action")
        # A rule-decided row IS the calendar's answer, so it tests the derivation.
        if decided_by == "rule" and calendar != action:
            mismatches.append({"session": session, "ticker": ticker,
                               "recorded": action, "derived": calendar,
                               "rationale": body.get("rationale", "")})

        graded = settled.get(f"{session}|{ticker}") or {}
        # The model was shown the calendar's flag. On a session decided before the
        # release-time fix that flag was the buggy one, so a model hedge there rests
        # on an input the corrected calendar would not have given it - and comparing
        # it against the corrected calendar is comparing two different questions.
        # Those rows stay in the table, marked, and out of the headline counts.
        affected = session in SELECTOR_BUG_SESSIONS and action == "HEDGE"
        rows.append({
            "session": session, "ticker": ticker, "decided_by": decided_by,
            "action": action, "calendar": calendar, "flag": flag, "source": source,
            "flip": action != calendar, "selector_affected": affected,
            "rationale": body.get("rationale", ""),
            "quote": (body.get("reader") or {}).get("verbatim_quote", ""),
            "reasoning": (body.get("reader") or {}).get("reasoning", ""),
            "value_added_bp": graded.get("value_added_bp"),
            "settled": bool(graded),
        })

    rows.sort(key=lambda r: (r["session"], r["ticker"]))
    clean = [r for r in rows if not r["selector_affected"]]
    model = [r for r in clean if r["decided_by"] == "model"]
    flips = [r for r in model if r["flip"]]
    graded_flips = [r for r in flips if r["value_added_bp"] is not None]
    rule_rows = [r for r in rows if r["decided_by"] == "rule"]

    payload = {
        "built_on": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "vol_gate_enabled": DEFAULT_POLICY.vol_gate_enabled,
        "check": {
            "rule_rows": len(rule_rows),
            "matched": len(rule_rows) - len(mismatches),
            "mismatched": mismatches,
        },
        "counts": {
            "decisions": len(rows),
            "excluded": len(rows) - len(clean),
            "compared": len(clean),
            "model": len(model),
            "rule": len(rule_rows),
            "agreed": sum(1 for r in model if not r["flip"]),
            "flips": len(flips),
            "flips_to_hedge": sum(1 for r in flips if r["action"] == "HEDGE"),
            "flips_to_no_hedge": sum(1 for r in flips if r["action"] == "NO_HEDGE"),
            "derived": sum(1 for r in rows if r["source"] == "derived"),
            "recorded": sum(1 for r in rows if r["source"] == "recorded"),
        },
        "flip_value_added_bp": (round(sum(r["value_added_bp"] for r in graded_flips), 1)
                                if graded_flips else None),
        "flips_settled": len(graded_flips),
        "rows": rows,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n")
    return path


def load(path: Path | None = None) -> dict:
    path = _path(path)
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}


if __name__ == "__main__":
    p = build()
    d = json.loads(p.read_text())
    c, k = d["counts"], d["check"]
    print(f"wrote {p.name} ({p.stat().st_size:,} bytes)")
    print(f"  {c['decisions']} decisions · {c['model']} read by the model · "
          f"{c['flips']} changed the calendar's answer "
          f"({c['flips_to_hedge']} to HEDGE, {c['flips_to_no_hedge']} to NO_HEDGE)")
    print(f"  derivation check: {k['matched']}/{k['rule_rows']} rule-decided rows reproduced")
    for m in k["mismatched"]:
        print(f"    {m['session']} {m['ticker']}: ledger {m['recorded']} · derived {m['derived']}")
