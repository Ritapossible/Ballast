"""The event reader — where the LLM does the work only it can do.

The handbook defines this track as "the LLM is the primary trading decision-maker,
not just an assistant", and the measurements agree that a model is needed here:

  * Gate 1a — trailing volatility separates risky nights by only 1.41x, and the
    nights it picks carry compensated return. It is not a usable selector.
  * Gate 1b — the earnings calendar separates at 3.2x on uncompensated variance,
    so it is usable, but the replay showed it covers just 2 of the 6 worst
    position-nights. Scheduled earnings are a minority of the tail.

Reaching the rest means reading unstructured news. So the reader is handed the
night's headlines and the calendar flag, and returns the HEDGE / NO_HEDGE / ABSTAIN
judgment together with the facts behind it.

Its authority is real but bounded. It decides WHETHER to protect a position; it
never decides size, price or direction, and the enforcer still makes a directional
trade unreachable. Three gates stand between the model and an order:

  1. schema      — the answer parses into the contracted shape or it is refused
  2. identity    — the ticker must be the one asked about (never a substitute)
  3. grounding   — the verbatim quote must actually appear in the supplied
                   headlines, so a fabricated source cannot pass

A judgment failing any gate is discarded and the deterministic calendar rule runs
instead. Precision is a pipeline stage here, not a hope pinned to the prompt.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from enum import Enum

from . import llm
from .news import NewsItem
from .policy import EventType, Impact, NightRisk

MIN_CONFIDENCE = 0.5


class Judgment(str, Enum):
    HEDGE = "HEDGE"
    NO_HEDGE = "NO_HEDGE"
    ABSTAIN = "ABSTAIN"          # the model declines; the calendar rule takes over


class RejectReason(str, Enum):
    NO_MODEL = "model_unavailable"
    BAD_SCHEMA = "schema_violation"
    WRONG_TICKER = "ticker_mismatch"
    UNGROUNDED = "quote_not_in_sources"
    LOW_CONFIDENCE = "below_confidence_floor"


@dataclass(frozen=True)
class ReaderVerdict:
    ticker: str
    judgment: Judgment
    risk: NightRisk
    reasoning: str = ""
    model: str = ""
    accepted: bool = True
    rejected_because: RejectReason | None = None

    @property
    def usable(self) -> bool:
        return self.accepted and self.judgment is not Judgment.ABSTAIN

    def to_record(self) -> dict:
        return {
            "ticker": self.ticker,
            "judgment": self.judgment.value,
            "accepted": self.accepted,
            "rejected_because": self.rejected_because.value if self.rejected_because else None,
            "model": self.model,
            "reasoning": self.reasoning,
            "event_type": self.risk.event_type.value,
            "expected_impact": self.risk.expected_impact.value,
            "confidence": self.risk.confidence,
            "source_url": self.risk.source_url,
            "verbatim_quote": self.risk.verbatim_quote,
            "unknowns": list(self.risk.unknowns),
        }


SYSTEM = """You assess overnight risk for a holder of tokenized US equities.

The US primary market is closed but the token keeps trading, so the holder is \
exposed to whatever happens tonight and cannot sell into the underlying. They can \
buy a hedge that removes about 98% of the overnight move for roughly 11 basis \
points, and they want it only on nights where something can actually move the stock.

Judge ONE ticker for ONE overnight window.

Answer with a single JSON object and nothing else:

{
  "ticker": "<the exact ticker you were asked about>",
  "judgment": "HEDGE" | "NO_HEDGE" | "ABSTAIN",
  "event_type": "earnings" | "guidance" | "macro" | "legal" | "product" | "none",
  "expected_impact": "low" | "medium" | "high",
  "confidence": <0.0 to 1.0>,
  "verbatim_quote": "<one headline copied EXACTLY from the sources, or \\"\\">",
  "reasoning": "<two sentences at most>",
  "unknowns": ["<what you could not determine>"]
}

Rules:
- HEDGE only when a specific, identifiable event can move THIS stock tonight.
- Analyst opinion, price targets, ratings and general commentary are NOT events.
- verbatim_quote must be copied character-for-character from a supplied headline. \
Never paraphrase it and never invent one. If nothing supports your judgment, use "".
- ABSTAIN when the sources do not let you judge. Abstaining is correct and expected.
- You decide whether to protect the position. You never decide size or direction."""


def _prompt(ticker: str, session: dt.date, window_hours: float,
            items: list[NewsItem], earnings_flagged: bool) -> str:
    headlines = "\n".join(f"- {i.as_context()}" for i in items) or "- (no headlines found)"
    return (
        f"Ticker: {ticker}\n"
        f"Overnight window: {session.isoformat()} close to next open "
        f"({window_hours:.1f} hours of exposure)\n"
        f"Scheduled earnings in this window (from the exchange calendar): "
        f"{'YES' if earnings_flagged else 'no'}\n\n"
        f"Headlines:\n{headlines}\n"
    )


def _reject(ticker: str, why: RejectReason, detail: str = "") -> ReaderVerdict:
    return ReaderVerdict(
        ticker=ticker, judgment=Judgment.ABSTAIN,
        risk=NightRisk(ticker=ticker, unknowns=(detail,) if detail else ()),
        accepted=False, rejected_because=why,
    )


def read(ticker: str, session: dt.date, window_hours: float,
         items: list[NewsItem], earnings_flagged: bool) -> ReaderVerdict:
    """Ask the model for a judgment, then refuse it unless it clears every gate."""
    if not llm.available():
        return _reject(ticker, RejectReason.NO_MODEL, "QWEN_API_KEY not set")

    try:
        completion = llm.complete(SYSTEM, _prompt(ticker, session, window_hours,
                                                  items, earnings_flagged))
        data = llm.parse_json_object(completion.text)
    except llm.LLMUnavailable as exc:
        return _reject(ticker, RejectReason.NO_MODEL, exc.detail)
    except llm.LLMBadOutput as exc:
        return _reject(ticker, RejectReason.BAD_SCHEMA, str(exc))

    # Gate 1 - schema
    try:
        judgment = Judgment(str(data["judgment"]).upper())
        event_type = EventType(str(data.get("event_type", "none")).lower())
        impact = Impact(str(data.get("expected_impact", "low")).lower())
        confidence = float(data.get("confidence", 0.0))
    except (KeyError, ValueError) as exc:
        return _reject(ticker, RejectReason.BAD_SCHEMA, f"{type(exc).__name__}: {exc}")

    # Gate 2 - identity. P13: never accept a judgment about a different instrument.
    if str(data.get("ticker", "")).upper().strip() != ticker.upper():
        return _reject(ticker, RejectReason.WRONG_TICKER,
                       f"model answered about {data.get('ticker')!r}")

    # Gate 3 - grounding. A quote must exist in what we supplied.
    quote = str(data.get("verbatim_quote", "")).strip()
    if quote and not any(quote.lower() in i.title.lower() for i in items):
        return _reject(ticker, RejectReason.UNGROUNDED,
                       f"quote not found in {len(items)} supplied headlines")
    if judgment is Judgment.HEDGE and not quote and not earnings_flagged:
        return _reject(ticker, RejectReason.UNGROUNDED,
                       "HEDGE with no supporting quote and nothing on the calendar")

    if judgment is Judgment.HEDGE and confidence < MIN_CONFIDENCE:
        return _reject(ticker, RejectReason.LOW_CONFIDENCE,
                       f"confidence {confidence:.2f} < {MIN_CONFIDENCE}")

    source_url = next((i.url for i in items if quote and quote.lower() in i.title.lower()), "")
    unknowns = tuple(str(u) for u in (data.get("unknowns") or [])[:5])

    return ReaderVerdict(
        ticker=ticker, judgment=judgment, model=completion.model,
        reasoning=str(data.get("reasoning", ""))[:400],
        risk=NightRisk(ticker=ticker, event_type=event_type, expected_impact=impact,
                       confidence=confidence, source_url=source_url,
                       verbatim_quote=quote, unknowns=unknowns),
    )
