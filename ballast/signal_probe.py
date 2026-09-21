"""What `bitget-signal` actually answers, measured rather than remembered.

The page used to say all 19 research tools returned an empty envelope, and that
this had been "confirmed to be the service and not this client". Both halves were
wrong, and the second one was wrong in a way worth writing down.

EVERY TOOL REQUIRES AN `action`. A call without one is not rejected at the
protocol level; it is answered. `technical_analysis` with no action returns
`{"error": "Unknown action: "}`, which is indistinguishable at a glance from the
`{"error": ""}` that a genuinely dead upstream returns. So a sweep that called
each tool bare reads an empty envelope back from every one of them and concludes
the service is down - including from the one tool that has real data behind it.
That is what happened here. The conclusion was drawn from a client error and
published as a measurement of the service.

WHAT IT ACTUALLY DOES. Asked properly, the service splits cleanly in two:

  * Catalogue actions - `sources`, `series_list`, `assets_list`, `platforms` -
    answer from static in-process tables, and answer instantly.
  * Fetch-backed actions - the news, the macro releases, the quotes - answer
    with an empty envelope. Whatever upstream they call is not returning.
  * `technical_analysis` is the exception, and the reason this module exists.
    It has its own OHLCV store, and it computes real indicators off it.

UNKNOWN IS NOT ZERO. Same rule as everywhere else here: a probe that could not
be reached is recorded as `unreachable` with the transport's own reason, never as
`empty`. "The service answered and had nothing" and "we could not ask" are
different findings and the page prints them differently.

WATCH THE YIELD CURVE ROW. `rates_yields/yield_curve` returns `spread_10y2y: 0.0`
and `inverted: false` on top of six maturities that each came back `{"error": ""}`.
A conclusion computed from six failures, presented as a fact. That is the exact
failure this whole project exists to argue against, found in a service we were
about to describe as simply "no data".

    python3 -m ballast.signal_probe      # -> state/signal_probe.json
"""
from __future__ import annotations

import datetime as dt
import json
from collections.abc import Callable
from pathlib import Path

from . import config, mcp

OUT_NAME = "signal_probe.json"

# The catalogue the service advertises over `tools/list`. Stated so the page can
# say "N of 19" and have the 19 come from somewhere rather than from memory.
TOOL_COUNT = 19

# A ticker no exchange lists. `technical_analysis` refuses it with "No OHLCV data
# for ZZZZQQ/4h" rather than inventing a number, which is how we know the RSIs it
# does return are computed from something and not generated to look busy.
CONTROL_TICKER = "ZZZZQQ"


def _path(given: Path | None) -> Path:
    return given or (config.STATE / OUT_NAME)


def _sized(payload: object, key: str) -> int:
    """How many entries a catalogue answered with."""
    if not isinstance(payload, dict):
        return 0
    return len(payload.get(key) or ())


def _articles(payload: object) -> int:
    """Articles across every feed - not feeds, which is the trap this measures.

    `news_feed` answers with one envelope per source. Counting the outer list
    gives 44 "headlines" that are really source names.
    """
    return len(mcp.signal_headlines(payload))


def _numeric_yields(payload: object) -> int:
    """Maturities that came back as numbers, ignoring the computed spread.

    The tool reports `spread_10y2y` and `inverted` whether or not any maturity
    resolved, so counting top-level keys would score this row as carrying data.
    """
    curve = payload.get("yield_curve") if isinstance(payload, dict) else None
    if not isinstance(curve, dict):
        return 0
    return sum(1 for v in curve.values() if isinstance(v, (int, float)))


def _indicator(payload: object) -> int:
    """1 if a real indicator value came back."""
    if not isinstance(payload, dict):
        return 0
    return 1 if isinstance(payload.get("rsi"), (int, float)) else 0


def _anything(payload: object) -> int:
    """Entries in a fetch-backed answer, counting empty error markers as nothing.

    `{"error": ""}`, `{"alt_me_error": ""}` and the transport's `{"text": "Error
    executing tool ..."}` fallback all mean the same thing: answered, carried
    nothing. None of them raise, so none of them can be detected by absence.
    """
    if isinstance(payload, list):
        return len(payload)
    if not isinstance(payload, dict):
        return 0
    if set(payload) == {"text"}:
        return 0
    return sum(1 for key, value in payload.items()
               if not key.endswith("error") and key != "note"
               and value not in ("", None, {}, []))


# (tool, action, extra arguments, kind, reader, unit). `kind` is the split the
# page reports: a catalogue answers from a table, a live action has to fetch.
Probe = tuple[str, str, dict, str, Callable[[object], int], str]

PROBES: tuple[Probe, ...] = (
    ("news_feed", "sources", {}, "catalog",
     lambda p: _sized(p, "feeds"), "feeds"),
    ("macro_indicators", "series_list", {}, "catalog",
     lambda p: _sized(p, "available_indicators"), "series"),
    ("rates_yields", "series_list", {}, "catalog",
     lambda p: _sized(p, "available_rates"), "rates"),
    ("cross_asset", "assets_list", {}, "catalog",
     lambda p: _sized(p, "assets"), "symbols"),
    ("social_trending", "platforms", {}, "catalog",
     lambda p: _sized(p, "platforms"), "platforms"),
    ("news_feed", "latest", {"limit": 5}, "live", _articles, "articles"),
    ("tradfi_news", "earnings", {}, "live", _anything, "entries"),
    ("tradfi_news", "news", {}, "live", _anything, "entries"),
    ("macro_indicators", "latest_release", {"indicator": "cpi"}, "live",
     _anything, "entries"),
    ("rates_yields", "yield_curve", {}, "live", _numeric_yields, "maturities"),
    ("sentiment_index", "current", {}, "live", _anything, "entries"),
    ("global_assets", "price", {"symbol": "AAPL"}, "live", _anything, "entries"),
    ("crypto_price", "price", {"symbol": "BTC"}, "live", _anything, "entries"),
    ("technical_analysis", "rsi", {"symbol": "AAPL"}, "live", _indicator,
     "indicators"),
)


def _probe(tool: str, action: str, extra: dict, reader, unit: str) -> dict:
    row = {"tool": tool, "action": action}
    try:
        payload = mcp.signal(tool, action=action, **extra)
    except mcp.McpUnavailable as exc:
        return {**row, "verdict": "unreachable", "count": None, "unit": unit,
                "detail": exc.reason[:160]}
    count = reader(payload)
    return {**row, "verdict": "data" if count else "empty", "count": count,
            "unit": unit, "detail": f"{count} {unit}"}


def coverage(tickers: list[str]) -> dict:
    """Which of the book's names `technical_analysis` can actually price.

    Ballast hedges US stocks. A crypto research service having an indicator
    endpoint means nothing unless it holds bars for the names in this book, so
    the question is asked of the book rather than of a convenient symbol.
    """
    answered: list[str] = []
    missing: list[str] = []
    unreachable: list[dict] = []
    for ticker in tickers:
        try:
            payload = mcp.signal("technical_analysis", action="rsi", symbol=ticker)
        except mcp.McpUnavailable as exc:
            unreachable.append({"ticker": ticker, "detail": exc.reason[:120]})
            continue
        (answered if _indicator(payload) else missing).append(ticker)
    control_refused = None
    try:
        control = mcp.signal("technical_analysis", action="rsi",
                             symbol=CONTROL_TICKER)
        control_refused = _indicator(control) == 0
    except mcp.McpUnavailable:
        control_refused = None
    return {"asked": len(tickers), "answered": sorted(answered),
            "missing": sorted(missing), "unreachable": unreachable,
            "control_ticker": CONTROL_TICKER, "control_refused": control_refused}


def _book_tickers() -> list[str]:
    try:
        book = json.loads((config.STATE / "book.json").read_text())
    except (OSError, json.JSONDecodeError):
        return []
    return [p["ticker"] for p in book.get("positions", []) if p.get("ticker")]


def build(out: Path | None = None) -> Path:
    rows = []
    for tool, action, extra, kind, reader, unit in PROBES:
        row = _probe(tool, action, extra, reader, unit)
        row["kind"] = kind
        rows.append(row)

    # A bare call is answered, not rejected, and its answer looks empty. Recorded
    # here because it is the reason the previous claim on this page was wrong.
    try:
        bare = mcp.signal("technical_analysis")
        bare_reply = json.dumps(bare, ensure_ascii=False)[:120]
    except mcp.McpUnavailable as exc:
        bare_reply = f"unreachable: {exc.reason[:100]}"

    live = [r for r in rows if r["kind"] == "live"]
    cat = [r for r in rows if r["kind"] == "catalog"]
    payload = {
        "built_on": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "source": mcp.SIGNAL_ENDPOINT,
        "tools_listed": TOOL_COUNT,
        "counts": {
            "probed": len(rows),
            "with_data": sum(1 for r in rows if r["verdict"] == "data"),
            "empty": sum(1 for r in rows if r["verdict"] == "empty"),
            "unreachable": sum(1 for r in rows if r["verdict"] == "unreachable"),
            "catalog_probed": len(cat),
            "catalog_with_data": sum(1 for r in cat if r["verdict"] == "data"),
            "live_probed": len(live),
            "live_with_data": sum(1 for r in live if r["verdict"] == "data"),
        },
        "no_action_reply": bare_reply,
        "coverage": coverage(_book_tickers()),
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
    c, cov = d["counts"], d["coverage"]
    print(f"wrote {p.name} ({p.stat().st_size:,} bytes)")
    print(f"  {c['catalog_with_data']}/{c['catalog_probed']} catalogue actions carry data")
    print(f"  {c['live_with_data']}/{c['live_probed']} live actions carry data"
          f" ({c['unreachable']} unreachable)")
    print(f"  book coverage: {len(cov['answered'])}/{cov['asked']}"
          f" · missing {', '.join(cov['missing']) or 'none'}")
    print(f"  no-action reply: {d['no_action_reply']}")
