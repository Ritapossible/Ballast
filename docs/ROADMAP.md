# Roadmap

What is still open, why, and what it would take. Ordered by how much it would change
the product, not by effort.

The **Defects** list in the documentation is a different thing and is not a backlog:
every item on it is already fixed. It stays published because a project that reports
only its successes has told you nothing about its error rate.

---

## Closed since the audit

| Was | Status |
|---|---|
| US exchange holidays not modelled | **Done.** `ballast/holidays.py` computes NYSE closures and early closes from rules, not a table, so the calendar cannot expire. A Good Friday window is now measured at 89.5 hours rather than mislabelled as an ordinary 17.5-hour overnight. |
| Cost and universe figures hardcoded in pages | **Done.** Rendered from `docs/facts.json`, regenerated nightly. They had already drifted from 219/699 to 224/704 unnoticed. |
| Fee and funding figures not reproducible | **Done.** `research/costs_study.py` verifies `ballast/costs.py` against the live schedule. |
| Model endpoint failures indistinguishable from abstentions | **Done.** Retry with backoff on 429/5xx, and the specific status recorded. |

---

## 1 · Does the reader close the tail-coverage gap?

**The open question the whole thesis rests on.** The calendar selector covered 2 of the
6 worst position-nights in replay; unscheduled events - macro, guidance, legal, product -
drive the rest, and the reader exists to reach them. That has not been measured.

It cannot be measured retrospectively without look-ahead: judging a past night needs
the headlines as they stood *before* the open, and Google News RSS does not serve a
point-in-time archive. So it has to accumulate forward.

**Needs:** roughly 30 sessions of live reader decisions, then a re-run of the
tail-coverage cohorts split by who decided.
**Blocked by:** wall-clock time. Roughly 4 of the ~30 sessions exist.
**Until then:** the site says coverage is incomplete rather than implying otherwise.

## 2 · Live execution through the Agentic Account

Fills are simulated against observed prices with the real fee schedule; the ledger is
exported in Bitget UTA order field names (`ballast/export.py`) so it reads alongside a
real log, but **no order reaches an exchange**.

`executor.Executor` is already the seam - a live implementation replaces one class and
nothing upstream changes.

**Needs:** OAuth credentials for a Bitget Agentic sub-account, then an executor calling
`POST /api/v2/mix/order/place-order` in demo mode.
**Blocked by:** account credentials, which are the operator's to issue.
**Risk if rushed:** an untested live-order path is worse than an honest simulated one.

## 3 · Position-level reporting for concentrated holders

The replay measures a 12-name equal-weight book, which is already diversified - so its
worst night is a market-wide move that hedging some names barely dents. The target user
holds one to ten positions. Position-level tail cohorts are computed but not surfaced on
the site.

**Needs:** a per-position view on `/settled`.
**Blocked by:** nothing. Next substantive feature.

## 4 · The 480 rTokens with no perp leg

Two thirds of the listed universe cannot be hedged at all. Ballast reports which, and
stops there.

**Possible:** hedge an unhedgeable name with a correlated proxy that does have a leg -
`rSMCI` against `NVDAUSDT`, say - and report the residual basis risk honestly.
**Blocked by:** needs its own measurement. A proxy hedge is a different product with a
different error profile, and claiming one without measuring it would be the sort of thing
the Defects list exists to prevent.

## 5 · Maker execution

All costs assume taker on both legs: 11.3 bp. Maker pricing would be ~3.3 bp - a third of
the cost, which materially widens the set of nights worth hedging.

**Needs:** a resting-order executor and measurement of the fill rate in a 4am perp book.
**Deliberately not assumed** until measured; an unfilled hedge is worse than an expensive
one.

## 6 · Reader coverage of the whole universe

The reader currently sees Google News RSS headlines. Earnings calls, filings and the
macro calendar are richer sources it does not read.

**Needs:** additional providers behind the same `NewsItem` interface. The grounding gate
already handles any source, since it only checks that a quote appears in what was supplied.

---

## Not planned

- **Predicting direction.** Gate 1b measured earnings nights as not reliably
  compensated; the product removes variance and makes no directional claim.
- **A volatility-based selector.** Measured at 1.41x separation on compensated nights.
  The gate exists in `policy.py` and ships disabled; re-enabling it needs new evidence.
- **Real capital.** Out of scope for this build.
