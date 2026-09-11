"""The decision: for each position, is tonight worth hedging?

Gate 1 (docs/RESEARCH.md §5) measured that trailing realised volatility separates
risky nights from ordinary ones by only 1.41x, while the same nights chosen with
hindsight separate at 13.2x. Risky nights exist; volatility cannot find them,
because overnight equity variance is driven by SCHEDULED EVENTS.

So the calendar leads and the statistic is a fallback, never the reverse.

`NightRisk` is the contract the event reader fills. In v0 it is populated from the
earnings calendar; from day 6 an LLM populates it from unstructured news. The shape
does not change, which is the point -- the model gains a source, never a decision.
"""
from __future__ import annotations

import datetime as dt
import statistics as st
from dataclasses import dataclass, field
from enum import Enum

from .costs import HEDGE_COST_BP


class Action(str, Enum):
    HEDGE = "HEDGE"
    NO_HEDGE = "NO_HEDGE"
    REDUCE = "REDUCE"          # reserved: idiosyncratic risk a correlation hedge cannot carry


class EventType(str, Enum):
    EARNINGS = "earnings"
    GUIDANCE = "guidance"
    MACRO = "macro"
    LEGAL = "legal"
    PRODUCT = "product"
    NONE = "none"


class Impact(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass(frozen=True)
class NightRisk:
    """What the reader may return. It may NOT return a size, price or decision."""
    ticker: str
    event_type: EventType = EventType.NONE
    scheduled_time: dt.datetime | None = None
    expected_impact: Impact = Impact.LOW
    confidence: float = 0.0
    source_url: str = ""
    verbatim_quote: str = ""
    unknowns: tuple[str, ...] = ()

    @property
    def is_scheduled_event(self) -> bool:
        return self.event_type is not EventType.NONE


@dataclass(frozen=True)
class PolicyConfig:
    hedge_cost_bp: float = HEDGE_COST_BP   # from costs.py: taker round trip net of funding
    vol_window: int = 20               # trailing nights
    min_history: int = 30              # need a distribution, not just a window
    vol_gate_enabled: bool = False     # see below - measured OFF, deliberately
    vol_percentile: float = 0.95       # if re-enabled, only a name's own extreme tail
    sigma_floor_bp: float = 60.0       # ...and never below this absolute level

    # WHY THE VOLATILITY GATE IS OFF BY DEFAULT (docs/RESEARCH.md §5, §8)
    #
    # Gate 1a: trailing realised volatility separates risky nights from ordinary
    # ones by only 1.41x, and the nights it selects carry POSITIVE expected return
    # (+19.3bp, t=3.08). Hedging them forgoes compensated return and pays 11.3bp
    # for the privilege. In the first replay it hedged 45% of nights and cost ~13%
    # a year.
    #
    # Gate 1b: the earnings calendar separates at 3.2x (median 3.0x per name) and
    # those nights are NOT reliably compensated -- pooled mean -61bp, t=-1.59, and
    # 0 of 15 names significant at |t|>=2. That is uncompensated variance, which is
    # exactly what a hedge should remove.
    #
    # So the calendar selects and the statistic does not. Turning this back on
    # requires new evidence, not a hunch.


@dataclass(frozen=True)
class Decision:
    ticker: str
    spot_symbol: str
    action: Action
    sigma_bp: float
    cost_bp: float
    risk: NightRisk
    rationale: str
    window_hours: float
    inputs: dict = field(default_factory=dict)

    def to_record(self) -> dict:
        return {
            "ticker": self.ticker,
            "spot_symbol": self.spot_symbol,
            "action": self.action.value,
            "sigma_bp": round(self.sigma_bp, 1),
            "cost_bp": round(self.cost_bp, 1),
            "window_hours": round(self.window_hours, 1),
            "rationale": self.rationale,
            "event": {
                "type": self.risk.event_type.value,
                "impact": self.risk.expected_impact.value,
                "confidence": self.risk.confidence,
                "source_url": self.risk.source_url,
                "verbatim_quote": self.risk.verbatim_quote,
                "unknowns": list(self.risk.unknowns),
            },
            "inputs": self.inputs,
        }


def forecast_sigma_bp(history: list[float], cfg: PolicyConfig) -> float | None:
    """Trailing 1-sigma overnight move in bp, from strictly prior nights."""
    window = history[-cfg.vol_window:]
    if len(window) < min(cfg.vol_window, cfg.min_history):
        return None
    return st.pstdev(window) * 1e4


def sigma_percentile(history: list[float], cfg: PolicyConfig) -> float | None:
    """Where tonight's forecast sits in this name's OWN history of forecasts.

    Every value is computed from data strictly prior to the night it describes, so
    the ranking carries no look-ahead.
    """
    if len(history) < cfg.min_history + cfg.vol_window:
        return None
    past = [st.pstdev(history[i - cfg.vol_window:i]) * 1e4
            for i in range(cfg.vol_window, len(history))]
    current = forecast_sigma_bp(history, cfg)
    if current is None or not past:
        return None
    return sum(1 for v in past if v <= current) / len(past)


def decide(ticker: str, spot_symbol: str, history: list[float], risk: NightRisk,
           window_hours: float, cfg: PolicyConfig = PolicyConfig(),
           model_judgment: str | None = None) -> Decision:
    """History must contain only nights strictly BEFORE the one being decided.

    `model_judgment` is the event reader's call — "HEDGE" or "NO_HEDGE" — and it
    LEADS when present. The handbook defines this track as "the LLM is the primary
    trading decision-maker", and the measurements agree: the calendar reaches only
    a minority of the tail (docs/RESEARCH.md §7), so something has to read the
    unscheduled events, and that reader should own the call it is making.

    Its authority stops at the judgment. Size, price and direction stay here and in
    the enforcer, so a model saying HEDGE can only ever cause a bounded hedge
    against a position that already exists — never a directional trade.

    Pass None when the reader abstained, was unavailable, or failed a gate; the
    deterministic calendar rule then runs unchanged.
    """
    sigma = forecast_sigma_bp(history, cfg)
    pct = sigma_percentile(history, cfg)

    if model_judgment == "HEDGE":
        return Decision(
            ticker=ticker, spot_symbol=spot_symbol, action=Action.HEDGE,
            sigma_bp=sigma or 0.0, cost_bp=cfg.hedge_cost_bp, risk=risk,
            rationale=(f"event reader judged HEDGE - {risk.event_type.value} "
                       f"({risk.expected_impact.value} impact, "
                       f"confidence {risk.confidence:.0%})"),
            window_hours=window_hours,
            inputs={"decided_by": "model", "history_nights": len(history)},
        )
    if model_judgment == "NO_HEDGE":
        return Decision(
            ticker=ticker, spot_symbol=spot_symbol, action=Action.NO_HEDGE,
            sigma_bp=sigma or 0.0, cost_bp=cfg.hedge_cost_bp, risk=risk,
            rationale="event reader judged NO_HEDGE - nothing tonight can move this name",
            window_hours=window_hours,
            inputs={"decided_by": "model", "history_nights": len(history)},
        )

    # No usable judgment: fall back to the calendar. Gate 1b measured it separates
    # at 3.2x on uncompensated variance, which volatility (1.41x) does not.
    if risk.is_scheduled_event and risk.expected_impact in (Impact.MEDIUM, Impact.HIGH):
        action = Action.HEDGE
        rationale = (f"scheduled {risk.event_type.value} tonight "
                     f"({risk.expected_impact.value} impact) - calendar selector")
    elif not cfg.vol_gate_enabled:
        action = Action.NO_HEDGE
        rationale = (f"nothing scheduled tonight - 1-sigma {sigma or 0:.0f}bp is not a "
                     f"reason to spend {cfg.hedge_cost_bp:.1f}bp (Gate 1a: vol separates "
                     f"only 1.41x and its nights are compensated)")
    elif sigma is None or pct is None:
        action = Action.NO_HEDGE
        rationale = (f"insufficient history ({len(history)} nights, "
                     f"need {cfg.min_history + cfg.vol_window})")
    elif pct >= cfg.vol_percentile and sigma >= cfg.sigma_floor_bp:
        action = Action.HEDGE
        rationale = (f"1-sigma {sigma:.0f}bp is in this name's own top "
                     f"{100 * (1 - cfg.vol_percentile):.0f}% (p{100 * pct:.0f}) - "
                     f"unusually risky night")
    elif sigma < cfg.sigma_floor_bp:
        action = Action.NO_HEDGE
        rationale = (f"1-sigma {sigma:.0f}bp below the {cfg.sigma_floor_bp:.0f}bp floor - "
                     f"not worth {cfg.hedge_cost_bp:.1f}bp")
    else:
        action = Action.NO_HEDGE
        rationale = (f"1-sigma {sigma:.0f}bp is ordinary for this name "
                     f"(p{100 * pct:.0f}) and nothing is scheduled")

    return Decision(
        ticker=ticker, spot_symbol=spot_symbol, action=action,
        sigma_bp=sigma or 0.0, cost_bp=cfg.hedge_cost_bp, risk=risk,
        rationale=rationale, window_hours=window_hours,
        inputs={"decided_by": "rule", "history_nights": len(history),
                "sigma_percentile": round(pct, 3) if pct is not None else None,
                "vol_percentile_gate": cfg.vol_percentile,
                "sigma_floor_bp": cfg.sigma_floor_bp},
    )
