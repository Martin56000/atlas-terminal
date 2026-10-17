"""Risk metrics. Pure functions, exactly the definitions in the spec.

All inputs are pandas Series of adjusted closes indexed by date (completed
trading days only). Window = last `window` daily log returns (window+1 prices).
"""
import math

import numpy as np
import pandas as pd

TRADING_DAYS = 252


def log_returns(prices: pd.Series) -> pd.Series:
    """r_t = ln(P_t / P_{t-1})"""
    p = prices.dropna().astype(float)
    return np.log(p / p.shift(1)).dropna()


def window_prices(prices: pd.Series, window: int = TRADING_DAYS) -> pd.Series:
    """Last window+1 prices -> exactly `window` returns."""
    return prices.dropna().iloc[-(window + 1):]


def annualized_volatility(r: pd.Series) -> float:
    """std(r, ddof=1) * sqrt(252)"""
    return float(r.std(ddof=1) * math.sqrt(TRADING_DAYS))


def annualized_return(r: pd.Series) -> float:
    """mean(r) * 252"""
    return float(r.mean() * TRADING_DAYS)


def sharpe_ratio(ann_return: float, ann_vol: float, rf: float):
    """(annualized return - rf) / annualized volatility. None if vol is 0."""
    if ann_vol is None or ann_vol == 0 or not math.isfinite(ann_vol):
        return None
    return float((ann_return - rf) / ann_vol)


def beta(r_stock: pd.Series, r_bench: pd.Series):
    """cov(r_s, r_b, ddof=1) / var(r_b, ddof=1), on common dates (inner join)."""
    df = pd.concat([r_stock.rename("s"), r_bench.rename("b")], axis=1, join="inner").dropna()
    if len(df) < 2:
        return None
    var_b = df["b"].var(ddof=1)
    if var_b == 0:
        return None
    return float(df["s"].cov(df["b"], ddof=1) / var_b)


def max_drawdown(prices: pd.Series) -> float:
    """Largest peak-to-trough decline, as a negative fraction (e.g. -0.25)."""
    p = prices.dropna().astype(float)
    running_peak = p.cummax()
    dd = p / running_peak - 1.0
    return float(dd.min())


def correlation_matrix(returns: dict) -> pd.DataFrame:
    """Pearson correlation of daily returns on common dates."""
    df = pd.concat(returns, axis=1, join="inner").dropna()
    return df.corr()


def risk_metrics(prices: pd.Series, bench_prices: pd.Series, rf: float, window: int = TRADING_DAYS) -> dict:
    """All metrics for one ticker over the last `window` returns."""
    p = window_prices(prices, window)
    r = log_returns(p)
    b = log_returns(window_prices(bench_prices, window))
    vol = annualized_volatility(r) if len(r) >= 2 else None
    ret = annualized_return(r) if len(r) >= 1 else None
    return {
        "n_returns": int(len(r)),
        "start": str(p.index[0].date()) if len(p) else None,
        "end": str(p.index[-1].date()) if len(p) else None,
        "ann_vol": vol,
        "ann_return": ret,
        "rf": rf,
        "sharpe": sharpe_ratio(ret, vol, rf) if (ret is not None and vol is not None and rf is not None) else None,
        "beta": beta(r, b),
        "max_drawdown": max_drawdown(p) if len(p) else None,
        # simple total return over the window (adjusted closes, dividends included): P_end / P_start - 1
        "perf_window": float(p.iloc[-1] / p.iloc[0] - 1) if len(p) >= 2 else None,
    }


def perf_stats(dates, closes):
    """Simple returns over standard horizons from completed daily closes (oldest first).
    1W = 5 sessions, 1M = 21, 3M = 63, 1Y = 252; YTD = vs the last close of the previous year."""
    out = {}
    if not closes:
        return out
    last = closes[-1]
    for key, n in (("w1", 5), ("m1", 21), ("m3", 63), ("y1", 252)):
        out[key] = (last / closes[-1 - n] - 1) if len(closes) > n and closes[-1 - n] else None
    year = dates[-1][:4]
    prev = [c for d, c in zip(dates, closes) if d[:4] < year]
    out["ytd"] = (last / prev[-1] - 1) if prev and prev[-1] else None
    window = closes[-252:]
    out["hi52"], out["lo52"] = max(window), min(window)
    out["last_close"], out["last_date"] = last, dates[-1]
    return out
