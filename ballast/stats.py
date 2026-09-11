"""Minimal statistics helpers. No dependencies, so `make research` needs no install."""
from __future__ import annotations

import math
import statistics as st


def ols(x: list[float], y: list[float]) -> tuple[float, float, list[float]]:
    """Univariate OLS. Returns (beta, r_squared, residuals)."""
    if len(x) != len(y) or len(x) < 3:
        raise ValueError("need at least 3 paired observations")
    mx, my = st.mean(x), st.mean(y)
    sxx = sum((u - mx) ** 2 for u in x)
    if sxx == 0:
        raise ValueError("zero variance in regressor")
    beta = sum((u - mx) * (v - my) for u, v in zip(x, y, strict=True)) / sxx
    resid = [v - my - beta * (u - mx) for u, v in zip(x, y, strict=True)]
    vy = st.pvariance(y)
    r2 = 1 - st.pvariance(resid) / vy if vy else float("nan")
    return beta, r2, resid


def t_stat(a: list[float]) -> tuple[float, float]:
    """(mean, t) for H0: mean == 0."""
    if len(a) < 8:
        return float("nan"), float("nan")
    m, s = st.mean(a), st.stdev(a)
    return m, m / (s / math.sqrt(len(a))) if s else float("nan")


def percentile(a: list[float], p: float) -> float:
    s = sorted(a)
    return s[min(int(p * len(s)), len(s) - 1)]


def bp(x: float) -> float:
    return x * 1e4
