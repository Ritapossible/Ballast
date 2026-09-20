# Ballast Overnight Protection

The protection leg of Ballast's overnight hedge, published on its own so its
cost can be measured rather than asserted.

**This is not an alpha strategy.** It shorts the matched RWA perpetual from the
US cash close to the next opening bell, and only on nights carrying a scheduled
company event. Every other night it holds nothing.

Read the return figure as the price of removing those nights, and drawdown as
the figure that matters. On a protected night where the stock rises, the short
gives that gain back — that is the premium working as designed, the same way an
insurance payment is a cost in a year without a fire.

- Symbols: 10 Bitget RWA stock perpetuals, confirmed `symbolStatus: normal`,
  `isRwa: YES` against the public contract config at authoring time.
- Replay: 1h bars, 2026-06-21 → 2026-09-18.
- Protected nights: the 10 real earnings dates falling in that window, taken
  from the same Nasdaq calendar the live Ballast selector uses.
- Setting `event_dates` to an empty mapping protects every night — the
  indiscriminate baseline the research rejects, kept reachable so the
  comparison can be run instead of claimed.

## Live vs replay

The replay reads `strategy_config.event_dates` - the ten nights inside the
backtest window. Every one of them is now in the past, so a live run reading
only those would hold nothing on every night for the rest of time.

The live path therefore asks the platform's own earnings calendar
(`equity.calendar.earnings`) which nights are scheduled in the next 45 days, and
applies the same `window.should_protect` rule the replay applies. Dates only,
never the content of a report: a scheduled release means tonight is dangerous,
not that the print will be good.

**If that calendar cannot be reached, it holds.** `should_protect` reads an
empty mapping as "protect every night" - the indiscriminate baseline the
research measured as value destroying - so failing open would land in the one
policy this package exists to reject. The empty-calendar branch emits `hold` for
every name and says which lookup failed.

One opening order exists in this package and it is a short. There is no branch
that opens a long.

## Measured

Published as **v0.0.2** on 2026-09-20. Sandbox run `pbrun-60a1da0970b5`,
over 2026-06-21 → 2026-09-18, on a real 2,121-point equity curve
(`curve_hash 096c4d1e…f433f`):

| | |
|---|---|
| total return | **−1.48%** |
| max drawdown | **3.76%** |
| win rate | 0.40 |
| total trades | 20 |
| Sharpe | −0.76 |

**Read those percentages on the right denominator.** The run record reports them
on the strategy basis — `net_pnl / margin_budget`, so −1.48% is **−29.62 USDT
against a 2,000 USDT budget**, not 1.48% of an account.

The **public GetAgent card quotes the same run on the account basis**: −0.03%
return, 0.08% max drawdown, against the 100,000 USDT the sandbox opened with.
Win rate, trade count and Sharpe are identical on both because ratios do not
depend on the denominator.

| | strategy basis (run record) | account basis (public card) |
|---|---|---|
| denominator | 2,000 USDT margin budget | 100,000 USDT starting balance |
| total return | −1.48% | −0.03% |
| max drawdown | 3.76% | 0.08% |
| net P&L | −29.62 USDT | −29.62 USDT |

One run, one loss, two denominators. Quoting either without naming which would
flatter or frighten depending on what a reader assumed, so both are here.

**Reproducible, not a snapshot.** The same package was replayed twice, two
days apart — `pbrun-e920a23cc1c7` at 2026-09-20 00:33Z and `pbrun-60a1da0970b5`
at 14:53Z. The platform returned the same five figures to four significant
digits *and the same NAV curve hash*, `096c4d1e…f433f`. The replay window is
pinned to closed bars, so a run taken a week from now should still land on that
hash; if it does not, something changed upstream and the figure here is stale.

**The negative return is the product, not a failure of it.** This Playbook buys
protection on 10 scheduled-event nights and holds nothing on the other ~55. Over
a window in which these names mostly rose, the shorts gave those gains back and
the premium was a pure cost — which is what an insurance payment looks like in a
year without a fire.

Read the drawdown, not the Sharpe. A ratio computed across 10 protected nights
is a description of those ten nights, not evidence of an edge, and the package
says so in its own description rather than leaving a reader to work it out.

What it does **not** show is whether the protection was worth buying. That needs
the spot leg it is hedging, which this harness cannot hold — see the full project.

Full project: https://github.com/Ritapossible/Ballast

## 策略说明

**策略**：隔夜保护对冲的做空腿。仅在有已排定公司事件的夜间持仓，其余时间空仓。

**开仓**：美股现货收盘时，对匹配的 RWA 永续合约开立空头头寸。

**平仓**：次日开盘时平掉该空头头寸。

**风险**：这不是 alpha 策略，不做方向性判断。在标的上涨的受保护夜间，空头会回吐涨幅，
该成本即为保险费本身。请将回报率读作移除这些夜间风险的价格，并以最大回撤作为主要衡量指标。
由于已排定事件稀疏，本 Playbook 交易次数很少，短窗口内的任何比率都只反映少数几个夜间。
