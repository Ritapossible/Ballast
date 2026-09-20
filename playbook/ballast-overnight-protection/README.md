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

## Measured

Sandbox run `pbrun-e920a23cc1c7`, 2026-09-20, over 2026-06-21 → 2026-09-18:

| | |
|---|---|
| total return | **−1.48%** |
| max drawdown | **3.76%** |
| win rate | 0.40 |
| total trades | 20 |
| Sharpe | −0.76 |

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
