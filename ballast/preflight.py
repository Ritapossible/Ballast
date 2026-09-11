"""Verify credentials and the live reader path without touching the ledger.

A scheduled run is a poor place to discover a bad key: the night is lost and the
paper-trading log has a hole in it that cannot be backfilled. This probes the whole
reader path against real news and the real endpoint, prints what came back, and
writes nothing anywhere.

    python -m ballast.preflight [TICKER]
"""
from __future__ import annotations

import datetime as dt
import sys

from . import config, llm
from .earnings import scheduled_in_window
from .news import NewsUnavailable, fetch, in_window
from .reader import read
from .sessions import UTC, close_utc, next_session, open_utc, window_hours

OK, BAD, WARN = "  ok  ", " FAIL ", " warn "


def _line(state: str, label: str, detail: str = "") -> None:
    print(f"[{state}] {label}" + (f"  {detail}" if detail else ""))


def run(ticker: str = "ORCL") -> int:
    print(f"Ballast preflight - {dt.datetime.now(UTC):%Y-%m-%d %H:%M} UTC\n")
    failures = 0

    # --- signing key -------------------------------------------------------
    if config.using_dev_secret():
        _line(WARN, "BALLAST_SECRET", "unset - signatures prove nothing")
    else:
        _line(OK, "BALLAST_SECRET", "set")

    # --- model credentials -------------------------------------------------
    if not llm.available():
        _line(BAD, "QWEN_API_KEY", "unset - the reader cannot run")
        return 1
    _line(OK, "QWEN_API_KEY", f"set · {llm.BASE_URL} · {llm.MODEL}")

    try:
        probe = llm.complete("Reply with the single word: ready.", "ready?", max_tokens=8)
        _line(OK, "endpoint", f"answered as {probe.model!r}")
    except llm.LLMUnavailable as exc:
        _line(BAD, "endpoint", str(exc))
        return 1

    # --- news source -------------------------------------------------------
    session = next_session(dt.datetime.now(UTC).date() - dt.timedelta(days=1))
    try:
        items = fetch(ticker)
    except NewsUnavailable as exc:
        # A preflight exists to tell these apart. "The feed is down" and "nothing
        # was published" need different responses from whoever is reading this.
        _line(BAD, "news", f"feed unreachable - {exc.reason}")
        items, failures = [], failures + 1
    if not items:
        _line(BAD, "news", f"no headlines for {ticker}")
        failures += 1
    else:
        windowed = in_window(items, close_utc(session), open_utc(next_session(session)))
        _line(OK, "news", f"{len(items)} headlines for {ticker} "
                          f"({len(windowed)} inside tonight's window)")

    # --- calendar ----------------------------------------------------------
    flagged = scheduled_in_window(ticker, session) is not None
    _line(OK, "calendar", f"{ticker} reporting in this window: {'YES' if flagged else 'no'}")

    # --- the full reader path ---------------------------------------------
    verdict = read(ticker, session, window_hours(session), items[:10], flagged)
    if verdict.accepted:
        _line(OK, "reader", f"{verdict.judgment.value} · {verdict.risk.event_type.value} · "
                            f"confidence {verdict.risk.confidence:.0%}")
        # Deliberately not printing the quote or the reasoning: these logs are
        # public on a public repository, and echoing model output from a
        # credentialed endpoint into them is a habit worth not forming. What
        # matters here is that the gates passed, which is already reported.
        print(f"         grounded: {'yes' if verdict.risk.verbatim_quote else 'no quote'}"
              f" · source: {'linked' if verdict.risk.source_url else 'none'}")
    else:
        # A refusal is a working gate, not a broken pipeline - say which one fired.
        _line(WARN, "reader", f"refused by gate: {verdict.rejected_because.value}")
        print("         the gates are doing their job; the calendar rule would decide")

    print(f"\nledger untouched · {'FAILURES: %d' % failures if failures else 'all checks passed'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(run(sys.argv[1] if len(sys.argv) > 1 else "ORCL"))
