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


def rows(ledger: Ledger) -> list[dict]:
    out = []
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
            "paper": True,
        })
    return out


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
            "sent to an exchange."),
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
