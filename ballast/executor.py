"""Execution. Paper only — no live fill is claimed anywhere in this project.

`PaperExecutor` fills against observed market prices and charges the real fee
schedule, defaulting to TAKER on both legs. Maker fills would be cheaper (~3.3bp
round trip versus 11.3bp) but a 4am perp book may not fill a resting order, so
maker pricing is treated as upside and never assumed.

The interface is deliberately narrow so a live executor backed by the Bitget
Agentic Account can replace this class without touching anything upstream.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Protocol

from .costs import PERP_MAKER_FEE, PERP_TAKER_FEE, SLIPPAGE_BP  # noqa: F401
from .enforcer import Admitted


@dataclass(frozen=True)
class Fill:
    perp_symbol: str
    side: str
    notional_usdt: float
    price: float
    fee_usdt: float
    slippage_bp: float
    at: dt.datetime
    paper: bool = True

    def to_record(self) -> dict:
        return {
            "perp_symbol": self.perp_symbol, "side": self.side,
            "notional_usdt": round(self.notional_usdt, 2),
            "price": self.price, "fee_usdt": round(self.fee_usdt, 4),
            "slippage_bp": self.slippage_bp,
            "at": self.at.isoformat(), "paper": self.paper,
        }


class Executor(Protocol):
    def execute(self, admitted: Admitted, mark: float, at: dt.datetime) -> Fill: ...


class PaperExecutor:
    """Fills an order the enforcer admitted. It cannot fill anything else.

    The signature is the point: there is no way to ask for a symbol, a side and a
    size. The only thing this accepts is an Admitted, which only the enforcer can
    issue and only to an intent that is opposite in sign to, and bounded by, a
    position already held. A caller that skips the enforcer has nothing to pass.
    """

    def __init__(self, fee: float = PERP_TAKER_FEE,
                 slippage_bp: float = SLIPPAGE_BP):
        self.fee = fee
        self.slippage_bp = slippage_bp

    def execute(self, admitted: Admitted, mark: float, at: dt.datetime) -> Fill:
        if not isinstance(admitted, Admitted):
            raise TypeError(
                "PaperExecutor.execute requires an Admitted issued by the enforcer; "
                f"got {type(admitted).__name__}")
        intent = admitted.intent
        if mark <= 0:
            raise ValueError(f"unusable mark for {intent.perp_symbol}: {mark}")
        if intent.notional_usdt <= 0:
            raise ValueError("notional must be positive")
        # Slippage always works against us, whichever way we are going.
        drift = self.slippage_bp / 1e4
        price = mark * (1 + drift) if intent.side == "buy" else mark * (1 - drift)
        return Fill(
            perp_symbol=intent.perp_symbol, side=intent.side,
            notional_usdt=intent.notional_usdt,
            price=price, fee_usdt=intent.notional_usdt * self.fee,
            slippage_bp=self.slippage_bp, at=at, paper=True,
        )
