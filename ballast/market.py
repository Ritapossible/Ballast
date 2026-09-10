"""Bitget public market data client.

Read-only, no API key. Two things here are easy to get wrong and are the reason
this module exists rather than inline requests:

1. Granularity casing differs by market: spot wants `1h`, futures wants `1H`.
   The wrong case returns an EMPTY data array with code `00000` -- a silent
   failure that looks like "no data" rather than an error.

2. `/market/candles` caps at 1000 bars (~43 days) and looks like a hard history
   limit. It is not. `/market/history-candles` with `endTime` pages backwards to
   467+ days of hourly rToken data.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE = "https://api.bitget.com"
CACHE = Path(__file__).resolve().parent.parent / ".cache" / "market"
_MAX_PAGE = 200


class BitgetError(RuntimeError):
    """The API answered with an error, or could not be reached."""


class MarketDataUnavailable(BitgetError):
    """A symbol returned no usable candles."""


def _get(url: str, retries: int = 3, backoff: float = 1.5) -> dict:
    last: Exception | None = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=30) as resp:
                payload = json.load(resp)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last = exc
            time.sleep(backoff ** attempt)
            continue
        if payload.get("code") != "00000":
            raise BitgetError(f"{payload.get('code')}: {payload.get('msg')} ({url})")
        return payload
    raise BitgetError(f"request failed after {retries} attempts: {url}") from last


def spot_symbols() -> list[dict]:
    return _get(f"{BASE}/api/v2/spot/public/symbols")["data"]


def futures_tickers() -> list[dict]:
    return _get(f"{BASE}/api/v2/mix/market/tickers?productType=usdt-futures")["data"]


def contract(symbol: str) -> dict:
    url = f"{BASE}/api/v2/mix/market/contracts?productType=usdt-futures&symbol={symbol}"
    return _get(url)["data"][0]


def funding_history(symbol: str, page_size: int = 100) -> list[dict]:
    url = (f"{BASE}/api/v2/mix/market/history-fund-rate"
           f"?symbol={symbol}&productType=usdt-futures&pageSize={page_size}")
    return _get(url)["data"]


def _history_url(symbol: str, market: str, granularity: str, end_ms: int) -> str:
    if market == "spot":
        return (f"{BASE}/api/v2/spot/market/history-candles"
                f"?symbol={symbol}&granularity={granularity}"
                f"&endTime={end_ms}&limit={_MAX_PAGE}")
    return (f"{BASE}/api/v2/mix/market/history-candles"
            f"?symbol={symbol}&granularity={granularity}&productType=usdt-futures"
            f"&endTime={end_ms}&limit={_MAX_PAGE}")


def candles(symbol: str, market: str = "spot", granularity: str | None = None,
            max_bars: int = 12_000, use_cache: bool = True) -> list[list[str]]:
    """Hourly candles, oldest first, paged backwards via `endTime`.

    Returns raw Bitget rows: [ts_ms, open, high, low, close, base_vol, quote_vol].
    """
    if market not in ("spot", "mix"):
        raise ValueError(f"market must be 'spot' or 'mix', got {market!r}")
    granularity = granularity or ("1h" if market == "spot" else "1H")

    cache_file = CACHE / f"{symbol}_{market}_{granularity}.json"
    if use_cache and cache_file.exists():
        return json.loads(cache_file.read_text())

    end_ms = int(time.time() * 1000)
    seen: dict[int, list[str]] = {}
    while len(seen) < max_bars:
        rows = _get(_history_url(symbol, market, granularity, end_ms)).get("data") or []
        fresh = [r for r in rows if int(r[0]) not in seen]
        if not fresh:
            break
        for r in fresh:
            seen[int(r[0])] = r
        end_ms = min(int(r[0]) for r in fresh)

    out = [seen[k] for k in sorted(seen)]
    if use_cache:
        CACHE.mkdir(exist_ok=True)
        cache_file.write_text(json.dumps(out))
    return out


def closes(symbol: str, market: str = "spot", **kw) -> dict[int, float]:
    """{timestamp_ms: close} — the form every study here consumes."""
    return {int(r[0]): float(r[4]) for r in candles(symbol, market, **kw)}


def bars(symbol: str, market: str = "spot", **kw) -> dict[int, tuple[float, float]]:
    """{timestamp_ms: (open, close)} — the form the overnight studies consume."""
    return {int(r[0]): (float(r[1]), float(r[4])) for r in candles(symbol, market, **kw)}
