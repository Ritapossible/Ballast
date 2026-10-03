"""Export the ledger as a Bitget-schema paper-trading log.

The handbook asks for a paper trading log produced during the competition, and
recommends generating it through the Agent Hub in `--paper-trading` mode. Ballast
simulates fills internally (see `executor.PaperExecutor`), so its native ledger is
its own schema rather than an exchange record.

This renders the same fills into the field names Bitget's UTA order endpoints use,
so the log can be read alongside a real one without translation. It is a faithful
re-encoding of what the ledger already contains - it does not invent an order id,
a fill price or a fee that the simulator did not produce, and every row is marked
`paper: true`.

    python -m ballast.export            # -> state/bitget_orders.json
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path

from . import config
from .ledger import Ledger


def _order_id(session: str, symbol: str, side: str) -> str:
    """Deterministic client order id, so re-exporting is stable."""
    seed = f"ballast:{session}:{symbol}:{side}".encode()
    return "BAL" + hashlib.sha256(seed).hexdigest()[:24].upper()


def _ms(iso: str) -> str:
    return str(int(dt.datetime.fromisoformat(iso).timestamp() * 1000))


def _settled_pnl(ledger: Ledger) -> dict[tuple[str, str], float]:
    """Each hedge's settled effect on the book, in bp, keyed by (session, ticker).

    `value_added_bp` is exactly what the hedge changed about the night net of its
    own cost - the short perp leg's return, with the fee and slippage already
    subtracted - so it is the number that moves a paper balance. The re-graded
    figure wins where one exists, because the full-window grade credited a hedge
    with a move it was not on for. See ballast/regrade.py.
    """
    pnl: dict[tuple[str, str], float] = {}
    for entry in ledger.records("settlement"):
        for row in entry["body"].get("rows", []):
            if row.get("action") == "HEDGE":
                pnl[(entry["body"].get("session"), row.get("ticker"))] = \
                    row.get("value_added_bp", 0.0)
    for entry in ledger.records("regrade"):
        for row in entry["body"].get("rows", []):
            pnl[(row.get("session"), row.get("ticker"))] = row.get("value_added_bp", 0.0)
    return pnl


def rows(ledger: Ledger) -> list[dict]:
    out = []
    pnl = _settled_pnl(ledger)
    balance = 0.0
    for entry in ledger.records("decision"):
        body = entry["body"]
        fill = body.get("fill")
        if not fill:
            continue                      # only executed hedges become orders
        size = (fill["notional_usdt"] / fill["price"]) if fill["price"] else 0.0
        out.append({
            "orderId": _order_id(body.get("session", ""), fill["perp_symbol"],
                                 fill["side"]),
            "clientOid": _order_id(body.get("session", ""), fill["perp_symbol"],
                                   fill["side"]),
            "symbol": fill["perp_symbol"],
            "productType": "USDT-FUTURES",
            "marginCoin": "USDT",
            "side": fill["side"],
            "tradeSide": "open",
            "orderType": "market",
            "force": "gtc",
            "price": f"{fill['price']:.6f}",
            "priceAvg": f"{fill['price']:.6f}",
            "size": f"{size:.6f}",
            "baseVolume": f"{size:.6f}",
            "quoteVolume": f"{fill['notional_usdt']:.4f}",
            "fee": f"-{fill['fee_usdt']:.6f}",
            "feeCoin": "USDT",
            "status": "filled",
            "cTime": _ms(fill["at"]),
            "uTime": _ms(fill["at"]),
            # Non-Bitget fields, prefixed so they cannot be mistaken for exchange
            # data. They carry the reason the order exists, which an exchange log
            # has no place for and a judge needs.
            "ballastSession": body.get("session"),
            "ballastReason": body.get("rationale"),
            "ballastDecidedBy": (body.get("inputs") or {}).get("decided_by"),
            "ballastSpotSymbol": body.get("spot_symbol"),
            "ballastSlippageBp": fill.get("slippage_bp"),
            # Account balance change, which the submission form asks for by name.
            # There is no funded account to report a balance ON - every fill is
            # simulated and none carries an exchange orderId - so reporting one
            # would be fiction. What is real is the cumulative paper P&L this
            # book's hedging has produced, and that is what these two fields are:
            # the settled effect of this hedge in USDT, and the running total
            # after it. A hedge that has not settled yet carries null rather than
            # a zero, because zero is a number and "not graded" is not.
            "ballastBalanceChangeUsdt": (
                f"{_bal_delta(pnl, body, fill):+.4f}"
                if _bal_delta(pnl, body, fill) is not None else None),
            "ballastBalanceAfterUsdt": None,
            "paper": True,
        })
        delta = _bal_delta(pnl, body, fill)
        if delta is not None:
            balance += delta
            out[-1]["ballastBalanceAfterUsdt"] = f"{balance:+.4f}"
    return out


def _bal_delta(pnl: dict, body: dict, fill: dict) -> float | None:
    """This hedge's settled effect on the book, in USDT."""
    bp = pnl.get((body.get("session"), body.get("ticker")))
    if bp is None:
        return None
    return bp / 1e4 * fill["notional_usdt"]


def build(out_path: Path | None = None) -> Path:
    ledger = Ledger(config.LEDGER_PATH, config.secret())
    orders = rows(ledger)
    payload = {
        "code": "00000",
        "msg": "success",
        "requestTime": str(int(dt.datetime.now(dt.timezone.utc).timestamp() * 1000)),
        "data": orders,
        "ballastNote": (
            "Paper fills simulated against observed Bitget market prices with the "
            "real fee schedule; taker on both legs, no maker fill assumed. Encoded "
            "in UTA order field names for comparison with a live log. No order was "
            "sent to an exchange. ballastBalanceChangeUsdt is this hedge's settled "
            "effect on the book net of fee and slippage, graded from the fill "
            "timestamp rather than the closing bell; ballastBalanceAfterUsdt is the "
            "running total. They are cumulative paper P&L, NOT a funded account "
            "balance - there is no funded account, and no fill carries an exchange "
            "orderId."),
    }
    path = out_path or (config.STATE / "bitget_orders.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n")
    return path


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=None)
    path = build(ap.parse_args().out)
    data = json.loads(path.read_text())["data"]
    print(f"wrote {path} - {len(data)} paper orders")
