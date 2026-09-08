# research/

Every number quoted in `docs/RESEARCH.md`, `PLAN.md` and the submission is produced
by these scripts. No API key is required — all endpoints used here are public.

```bash
python3 research/universe.py            # hedgeable universe (219 of 699)
python3 research/hedge_study.py         # hedge quality, stress conditioning, tail
python3 research/gate1_selection.py     # Gate 1: ex-ante selectability
python3 research/gate1_selection.py --lookahead   # the invalid version, for contrast
```

Responses are cached under `research/.cache/`. Delete it to force a refetch.

## Module map

| Module | Responsibility |
|---|---|
| `sessions.py` | DST-correct US session calendar — the only place an hour is defined |
| `bitget.py` | Public market data; backwards paging; granularity-casing trap |
| `universe.py` | rToken ↔ perp pair resolution |
| `overnight.py` | Overnight return series built on `sessions` |
| `stats.py` | OLS, t-stats, percentiles — no third-party dependencies |
| `hedge_study.py` | Does the perp hedge work, and when |
| `gate1_selection.py` | Can risky nights be chosen in advance |

## Two rules

1. **No look-ahead.** Any selection rule sees strictly prior data.
   `gate1_selection.py --lookahead` exists solely to document the bug that
   contaminated the first run of this analysis.
2. **Nothing hardcodes a session hour.** The US close is 20:00 UTC under EDT and
   21:00 UTC under EST; both occur inside our sample. Use `sessions.py`.
