"""The nightly run: decide, enforce, execute, record.

Runs after the US close. For every position in the book it produces exactly one
decision, and every decision -- including every refusal -- is written to the
signed ledger. Refusals are evidence too: a night Ballast declined to hedge is
graded in the morning alongside the nights it did.

    python -m ballast.night [--dry-run]
"""
from __future__ import annotations

import argparse
import datetime as dt

from . import config
from .llm import available as llm_available
from .book import Book
from .earnings import symbols_on
from .enforcer import Enforcer, OrderIntent
from .ledger import Ledger
from .mandate import NightMandate, SignedMandate
from .market import closes
from .overnight import overnight_returns
from .news import fetch, in_window
from .policy import Action, EventType, Impact, NightRisk, PolicyConfig, decide
from .reader import Judgment, read
from .sessions import UTC, close_utc, next_session, open_utc, window_hours

# The nightly run needs recent history for the sigma it reports, not the full
# two-year series the research scripts page down. 100 sessions is ample and keeps
# a scheduled run to seconds rather than minutes.
HISTORY_BARS = 2_400

MAX_HEDGE_RATIO = 1.0
MAX_NOTIONAL_USDT = 100_000.0
MAX_ORDERS = 50


def current_session(now: dt.datetime) -> dt.date:
    """The most recent weekday session whose close has already passed."""
    day = now.date()
    while day.weekday() > 4 or now < close_utc(day):
        day -= dt.timedelta(days=1)
        while day.weekday() > 4:
            day -= dt.timedelta(days=1)
    return day


def calendar_risk(ticker: str, session: dt.date) -> tuple[NightRisk, bool]:
    """The deterministic half: is a report scheduled inside this window?"""
    flag = symbols_on(session).get(ticker) or symbols_on(next_session(session)).get(ticker)
    if flag is None:
        return NightRisk(ticker=ticker), False
    return NightRisk(
        ticker=ticker, event_type=EventType.EARNINGS, expected_impact=Impact.HIGH,
        confidence=1.0,
        source_url=f"https://api.nasdaq.com/api/calendar/earnings?date={session.isoformat()}",
        verbatim_quote=f"{ticker} scheduled to report ({flag})",
        unknowns=("exact release time not supplied for historical dates",),
    ), True


def assess(ticker: str, session: dt.date, use_reader: bool):
    """Calendar first, then the event reader. Returns (risk, judgment, verdict)."""
    risk, flagged = calendar_risk(ticker, session)
    if not use_reader:
        return risk, None, None

    start, end = close_utc(session), open_utc(next_session(session))
    items = in_window(fetch(ticker), start, end) or fetch(ticker)[:8]
    verdict = read(ticker, session, window_hours(session), items, flagged)
    if not verdict.usable:
        return risk, None, verdict          # abstained or failed a gate -> rule decides
    return verdict.risk, verdict.judgment.value, verdict


def run(dry_run: bool = False, no_reader: bool = False) -> dict:
    use_reader = not no_reader
    now = dt.datetime.now(UTC)
    session = current_session(now)
    expires = open_utc(next_session(session))

    book = Book.load(config.BOOK_PATH)
    ledger = Ledger(config.LEDGER_PATH, config.secret())

    spot_marks, histories, perp_marks = {}, {}, {}
    for pos in book:
        bars = closes(pos.spot_symbol, "spot", max_bars=HISTORY_BARS, use_cache=False)
        spot_marks[pos.spot_symbol] = bars[max(bars)]
        perp_bars = closes(pos.perp_symbol, "mix", max_bars=HISTORY_BARS, use_cache=False)
        perp_marks[pos.perp_symbol] = perp_bars[max(perp_bars)]
        prior = overnight_returns(bars)
        histories[pos.ticker] = [v for d, v in sorted(prior.items()) if d < session]

    mandate = NightMandate(
        issued_at=now, expires_at=expires, universe=book.symbols(),
        max_hedge_ratio=MAX_HEDGE_RATIO, max_notional_usdt=MAX_NOTIONAL_USDT,
        max_orders=MAX_ORDERS, account="paper",
    )
    signed = SignedMandate.issue(mandate, config.secret())
    enforcer = Enforcer(signed, config.secret())
    notionals = book.notionals(spot_marks)

    ledger.append("mandate", {
        "session": session.isoformat(), "expires_at": expires.isoformat(),
        "universe": list(mandate.universe), "max_hedge_ratio": mandate.max_hedge_ratio,
        "max_notional_usdt": mandate.max_notional_usdt, "max_orders": mandate.max_orders,
        "signature": signed.signature, "dev_secret": config.using_dev_secret(),
    }, now)

    from .executor import PaperExecutor
    executor = PaperExecutor()
    hedged = declined = 0

    for pos in book:
        risk, judgment, verdict = assess(pos.ticker, session, use_reader)
        decision = decide(pos.ticker, pos.spot_symbol, histories[pos.ticker], risk,
                          window_hours(session), model_judgment=judgment)
        record = decision.to_record()
        if verdict is not None:
            record["reader"] = verdict.to_record()
        record["session"] = session.isoformat()
        record["spot_mark"] = spot_marks[pos.spot_symbol]
        record["notional_usdt"] = round(notionals.get(pos.spot_symbol, 0.0), 2)

        if decision.action is not Action.HEDGE:
            declined += 1
            ledger.append("decision", record, now)
            continue

        held = notionals.get(pos.spot_symbol, 0.0)
        intent = OrderIntent(
            spot_symbol=pos.spot_symbol, perp_symbol=pos.perp_symbol,
            side="sell" if held > 0 else "buy",
            notional_usdt=abs(held) * MAX_HEDGE_RATIO,
            reason=decision.rationale,
        )
        verdict = enforcer.evaluate(intent, notionals, now)
        record["enforcer"] = {"admitted": verdict.admitted, "rule": verdict.rule,
                              "detail": verdict.detail}

        if verdict.rejected:
            declined += 1
            ledger.append("decision", record, now)
            continue

        if not dry_run:
            fill = executor.execute(intent.perp_symbol, intent.side, intent.notional_usdt,
                                    perp_marks[pos.perp_symbol], now)
            enforcer.commit(intent)
            record["fill"] = fill.to_record()
        hedged += 1
        ledger.append("decision", record, now)

    summary = {
        "session": session.isoformat(), "positions": len(book),
        "hedged": hedged, "declined": declined,
        "window_hours": round(window_hours(session), 1),
        "usage": enforcer.usage, "dry_run": dry_run,
        "reader": "on" if use_reader and llm_available() else "off (no QWEN_API_KEY)",
    }
    ledger.append("night_summary", summary, now)
    return summary


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="decide and record, place no fills")
    ap.add_argument("--no-reader", action="store_true", help="calendar rule only, skip the LLM")
    s = run(**vars(ap.parse_args()))
    print(f"session {s['session']} · window {s['window_hours']}h · reader {s['reader']}\n"
          f"{s['positions']} positions · {s['hedged']} hedged · {s['declined']} declined")
    if config.using_dev_secret():
        print("note: BALLAST_SECRET unset — signing with the development key")
