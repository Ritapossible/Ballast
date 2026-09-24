"""A second opinion on the calendar, from `bitget-mcp-server`.

The calendar selector is the single point the whole policy rests on. Gate 1b
measured that earnings nights separate risky from ordinary at 3.2x where trailing
volatility manages 1.41x, so the calendar decides which nights get protected - and
until now it had exactly one source. A single source that quietly changes its answer
is indistinguishable from one that is right.

This takes every decision already on the chain and asks the organiser's US-stock
data service the same question Nasdaq was asked: was this name reporting inside
this session's window? Then it publishes where the two agree and where they do not.

WHY IT DOES NOT DECIDE. The selector is not re-pointed at this source, and this
module is not in the nightly decision path. Changing what chooses the hedged nights
days before a submission would invalidate the very record the change is meant to
support. It audits; it does not vote.

UNREACHABLE IS NOT "NO EARNINGS". `mcp.query` raises rather than returning empty,
and a ticker whose second opinion could not be fetched is recorded as `unknown` with
the upstream's own status code - never as agreement, and never as a disagreement
that would imply Nasdaq was wrong.

    python3 -m ballast.crosscheck      # -> state/calendar_crosscheck.json
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from . import config, mcp
from .earnings import scheduled_in_window
from .ledger import Ledger
from .sessions import next_session

OUT_NAME = "calendar_crosscheck.json"

# Consecutive unreachable answers before the run stops asking, while nothing
# has answered yet. A service that is simply down should cost three calls and a
# recorded reason, not a ten-minute nightly collecting the same 503.
GIVE_UP_AFTER = 3

# Once the service HAS answered, the same rule is wrong. This upstream does not
# keep sessions alive and returns an intermittent 404, and a run that checked
# six tickers then met five of those in a row abandoned the remaining 109 as
# "stopped after 3 failures" - publishing 114 unknown for a service that was
# demonstrably working. Down and flaky are different faults and only the first
# is a reason to stop early, so after a success the run continues until a
# quarter of the rows have failed.
FLAKY_BUDGET = 0.25

# Keys the service might carry a report date under. Its payload shape is not
# contractual, so every candidate is tried and the row says which one answered -
# a silently missed field would read as "no earnings" for every name.
DATE_KEYS = ("date", "reportDate", "report_date", "earningsDate", "earnings_date",
             "fiscalDateEnding", "time", "datetime")



# Candidates in preference order. The first that the live catalog lists wins, so
# a rename costs one extra catalog call rather than a day of `unknown` rows.
CALENDAR_ENTRIES = ("equity_calendar", "equity_calendar_earnings")
_ENTRY_CACHE: list[str | None] = [None]


def calendar_entry() -> str:
    """Whichever earnings-calendar entry this service currently exposes.

    Pinning the id is what broke: the name changed upstream and every
    crosscheck row came back `Unknown entry_id`. Asking the catalog once per
    run costs one call and turns a silent rename into a working second opinion.
    """
    if _ENTRY_CACHE[0]:
        return _ENTRY_CACHE[0]
    try:
        listed = mcp.catalog("equity")
        entries = listed.get("entries") or listed.get("items") or []
        ids = {e.get("id") or e.get("entry_id") or e.get("key")
               for e in entries if isinstance(e, dict)}
    except mcp.McpUnavailable:
        ids = set()
    for candidate in CALENDAR_ENTRIES:
        if candidate in ids:
            _ENTRY_CACHE[0] = candidate
            return candidate
    # Nothing recognised: return the current best guess so the caller's own
    # error handling records an honest `unknown` rather than skipping the check.
    return CALENDAR_ENTRIES[0]



def _give_up(consecutive: int, answered: int, failures: int, total: int) -> bool:
    """Stop asking? Down and flaky are different faults.

    Nothing has answered and three in a row failed: the service is down, and
    grinding through the rest collects the same error twelve times.

    Something HAS answered: the failures are this upstream's intermittent 404
    rather than an outage, and abandoning the run throws away checks that would
    have succeeded. Keep going until a quarter of the rows have failed, which
    still exits a run that degrades halfway through.
    """
    if not answered:
        return consecutive >= GIVE_UP_AFTER
    return failures > max(GIVE_UP_AFTER, int(total * FLAKY_BUDGET))


def _path(given: Path | None) -> Path:
    return given or (config.STATE / OUT_NAME)


def _dates(payload: object) -> list[str]:
    """Every date-looking string in the response, wherever it is nested."""
    found: list[str] = []

    def walk(node: object) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key in DATE_KEYS and isinstance(value, str) and len(value) >= 10:
                    found.append(value[:10])
                else:
                    walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(payload)
    return found


def earnings_for(ticker: str, cache: dict | None = None) -> list[str]:
    """Every report date the service knows for this ticker.

    Cached per ticker, because the answer does not depend on the session: the
    first cut asked once per decision and made 96 calls where 12 would do. Against
    an upstream that has been answering 503, that was eleven minutes of retrying
    to learn one thing twelve times.
    """
    if cache is not None and ticker in cache:
        return cache[ticker]
    # The upstream renamed this entry. It was `equity_calendar_earnings`; the
    # catalog now lists `equity_calendar`, and the old id answers
    # "Unknown entry_id" - which this module correctly recorded as `unknown`
    # for all 120 rows rather than as agreement. That is the fail-closed rule
    # working, and it is also why the page went a day claiming a second opinion
    # it no longer had. The entry id is read from the live catalog rather than
    # pinned, so the next rename degrades to unknown instead of silently
    # checking nothing.
    dates = _dates(mcp.query(calendar_entry(), symbol=ticker))
    if cache is not None:
        cache[ticker] = dates
    return dates


def second_opinion(ticker: str, session: dt.date,
                   cache: dict | None = None) -> tuple[str, str]:
    """(verdict, detail) - "yes", "no", or "unknown" with the reason."""
    try:
        dates = earnings_for(ticker, cache)
    except mcp.McpUnavailable as exc:
        return "unknown", exc.reason
    window = {session.isoformat(), next_session(session).isoformat()}
    hits = sorted(set(dates) & window)
    if hits:
        return "yes", f"reports {hits[0]}"
    return "no", f"{len(dates)} dates returned, none in this window"


def _ledger() -> Ledger:
    try:
        return Ledger(config.LEDGER_PATH, config.secret())
    except config.UnsignedError:
        return Ledger(config.LEDGER_PATH, config.DEV_SECRET)


def build(out: Path | None = None, limit: int | None = None) -> Path:
    pairs: list[tuple[str, str]] = []
    for entry in _ledger().records("decision"):
        body = entry["body"]
        pair = (body.get("session"), body.get("ticker"))
        if all(pair) and pair not in pairs:
            pairs.append(pair)
    pairs.sort()
    if limit:
        pairs = pairs[-limit:]

    # One probe before 12 tickers' worth of retrying. An upstream that is down
    # should cost one round trip and a recorded reason, not a ten-minute job.
    reachable, why = mcp.available()
    rows: list[dict] = []
    cache: dict[str, list[str]] = {}
    consecutive = answered = failures = 0
    for session_s, ticker in pairs:
        session = dt.date.fromisoformat(session_s)
        nasdaq = scheduled_in_window(ticker, session)
        if not reachable:
            verdict, detail = "unknown", why
        elif _give_up(consecutive, answered, failures, len(pairs)):
            verdict, detail = "unknown", (
                f"stopped after {GIVE_UP_AFTER} failures with nothing answered"
                if not answered else
                f"stopped after {failures} failures on a flaky upstream")
        else:
            verdict, detail = second_opinion(ticker, session, cache)
            if verdict == "unknown":
                consecutive += 1
                failures += 1
            else:
                consecutive = 0
                answered += 1
        rows.append({
            "session": session_s, "ticker": ticker,
            "nasdaq": "yes" if nasdaq else "no",
            "bitget_mcp": verdict, "detail": detail,
            "agree": (verdict != "unknown"
                      and verdict == ("yes" if nasdaq else "no")),
        })

    checked = [r for r in rows if r["bitget_mcp"] != "unknown"]
    payload = {
        "built_on": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "source": mcp.ENDPOINT,
        "service": {"reachable": reachable, "detail": why},
        "counts": {
            "decisions": len(rows),
            "checked": len(checked),
            "unknown": len(rows) - len(checked),
            "agreed": sum(1 for r in checked if r["agree"]),
            "disagreed": sum(1 for r in checked if not r["agree"]),
        },
        "rows": rows,
    }
    path = _path(out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n")
    return path


def load(path: Path | None = None) -> dict:
    try:
        return json.loads(_path(path).read_text())
    except (OSError, json.JSONDecodeError):
        return {}


if __name__ == "__main__":
    p = build()
    d = json.loads(p.read_text())
    c = d["counts"]
    print(f"wrote {p.name} ({p.stat().st_size:,} bytes)")
    print(f"  service: {'reachable' if d['service']['reachable'] else 'UNAVAILABLE'}"
          f" - {d['service']['detail'][:90]}")
    print(f"  {c['decisions']} decisions · {c['checked']} second-checked · "
          f"{c['agreed']} agreed · {c['disagreed']} disagreed · {c['unknown']} unknown")
