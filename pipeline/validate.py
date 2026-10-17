"""Cross-check: for AAPL and MC.PA, the latest price and the 1Y volatility shown
on the site must match a manual calculation from the same yfinance data.

The manual calculation deliberately uses plain Python (math, loops) rather
than the pandas code in metrics.py, and a separate yfinance call path
(Ticker.history instead of yf.download)."""
import math

from . import config, store
from .market import completed_bars, safe_name

CHECK = ["AAPL", "MC.PA"]
PRICE_TOL = 1e-4   # relative
VOL_TOL = 1e-3     # relative (Yahoo may revise the last adjusted value between two calls)


def manual_vol(adj_closes, window=252):
    p = adj_closes[-(window + 1):]
    r = [math.log(p[i] / p[i - 1]) for i in range(1, len(p))]
    n = len(r)
    mean = sum(r) / n
    var = sum((x - mean) ** 2 for x in r) / (n - 1)
    return math.sqrt(var) * math.sqrt(252), n


def run():
    import yfinance as yf
    risk = (store.read("risk.json") or {}).get("data") or {}
    results = []
    for t in CHECK:
        hist_env = store.read(f"history/{safe_name(t)}.json") or {}
        site_hist = hist_env.get("data")
        site_vol = ((risk.get("metrics") or {}).get(t) or {}).get("ann_vol")
        df = yf.Ticker(t).history(period="2y", interval="1d", auto_adjust=False)
        if df is None or df.empty or "Adj Close" not in df.columns:
            raise RuntimeError(f"no yfinance history for {t} (cannot cross-check)")
        df.index = df.index.tz_localize(None).normalize()
        df = completed_bars(df, config.BY_TICKER[t]["exchange"])
        factor = 0.01 if (site_hist or {}).get("currency") == "GBP" else 1.0
        closes = [float(x) * factor for x in df["Close"].tolist()]
        adj = [float(x) * factor for x in df["Adj Close"].tolist()]
        mvol, n = manual_vol(adj)
        site_price = site_hist["close"][-1] if site_hist else None
        price_ok = site_price is not None and abs(site_price / closes[-1] - 1) <= PRICE_TOL
        vol_ok = site_vol is not None and abs(site_vol / mvol - 1) <= VOL_TOL
        results.append({
            "ticker": t, "date": df.index[-1].strftime("%Y-%m-%d"),
            "manual_last_close": closes[-1], "site_last_close": site_price, "price_match": price_ok,
            "manual_vol_1y": mvol, "site_vol_1y": site_vol, "vol_match": vol_ok, "n_returns": n,
        })
    return {"checks": results, "all_passed": all(r["price_match"] and r["vol_match"] for r in results)}
