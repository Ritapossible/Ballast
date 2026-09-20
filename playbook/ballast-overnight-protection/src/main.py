"""Sandbox entry point for the Ballast Overnight Protection Playbook.

Historical runs build one replay frame per symbol from the managed kline path
and hand them to the platform's backtest engine. The strategy decides purely
from each bar's timestamp, so nothing here can leak a future night into a past
decision.
"""
import math

from getagent import backtest, data, runtime

INTERVAL = "1h"
EXCHANGE = "bitget"
VENUE = "BITGET"


def _finite(value):
    return None if isinstance(value, float) and not math.isfinite(value) else value


def _run_historical() -> None:
    cfg = runtime.manifest.get("strategy_config", {}) or {}
    symbols = runtime.manifest.get("trading_symbols") or []
    if not symbols:
        runtime.emit_signal(action="watch", symbol="", confidence=0.0,
                            metrics={"rows": 0},
                            meta={"reason": "no trading_symbols declared"})
        return

    frames = {}
    empty = []
    for symbol in symbols:
        # closed_only leaves the forming candle out, so the same replay returns
        # the same numbers twice. A half-formed tail bar at the open would also
        # be the one bar that decides whether a night is covered.
        bars = data.crypto.futures.kline(symbol=symbol, interval=INTERVAL,
                                         limit=1000, exchange=EXCHANGE,
                                         closed_only=True)
        frame = backtest.prepare_frame(bars, datetime_index="date")
        if frame.empty:
            empty.append(symbol)
            continue
        frames[f"{symbol}.{VENUE}"] = frame

    if not frames:
        runtime.emit_signal(action="watch", symbol=symbols[0], confidence=0.0,
                            metrics={"rows": 0},
                            meta={"reason": f"no bars for {', '.join(empty)}"})
        return

    result = backtest.run(ohlcv_data=frames, spec=runtime.backtest_spec)
    summary = result.summary or {}
    raw = dict(result.raw or {})

    # The backend merges this report as the BASE, so a value left unset here
    # cannot be filled in from the signal later. Both are overwritten rather
    # than defaulted for that reason.
    net_pnl = float(summary.get("net_pnl") or 0.0)
    starting = 100000.0
    raw["net_pnl"] = net_pnl
    raw["total_return_pct"] = (net_pnl / starting) * 100.0 if starting else 0.0

    metrics = {k: _finite(v) for k, v in {
        "total_return_pct": raw["total_return_pct"],
        "max_drawdown_pct": summary.get("max_drawdown_pct"),
        "win_rate": summary.get("win_rate"),
        "total_trades": summary.get("total_trades"),
        "sharpe_ratio": summary.get("sharpe_ratio"),
        "symbols_replayed": len(frames),
        "symbols_without_bars": len(empty),
    }.items()}

    backtest.generate_chart(result)
    backtest.write_report(result, raw=raw)
    runtime.emit_signal(
        action="report", symbol=symbols[0], confidence=1.0, metrics=metrics,
        meta={"note": "protection leg in isolation; a loss on a rising tape is "
                      "the premium, not a failed signal",
              "protected_nights": cfg.get("event_dates", {})})


def _run_live() -> None:
    """Live path: decide, then let the managed runtime gate any follow-trade."""
    symbols = runtime.manifest.get("trading_symbols") or []
    for symbol in symbols:
        runtime.emit_signal_or_follow(
            action="watch", symbol=symbol, confidence=0.5,
            metrics={}, meta={"note": "awaiting the cash close"})


def main() -> None:
    if runtime.is_backtest:
        _run_historical()
    else:
        _run_live()


if __name__ == "__main__":
    main()
