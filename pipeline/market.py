"""Market data from Yahoo Finance via yfinance (delayed quotes, daily history)."""
import re
import time
from datetime import datetime, timezone

import exchange_calendars as xcals
import pandas as pd

from . import config, store

FIELDS = ["Open", "High", "Low", "Close", "Adj Close", "Volume"]
PRICE_FIELDS = ["Open", "High", "Low", "Close", "Adj Close"]


def safe_name(ticker: str) -> str:
    """File-system safe name; the website uses the same rule."""
    return re.sub(r"[^A-Za-z0-9.\-]", "_", ticker)


def with_retries(fn, attempts=4, base_delay=5):
    last = None
    for i in range(attempts):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001
            last = e
            if i < attempts - 1:
                time.sleep(base_delay * (2 ** i))
    raise last


def _download(tickers, **kw):
    import yfinance as yf

    def go():
        df = yf.download(tickers, auto_adjust=False, group_by="ticker", threads=True,
                         progress=False, **kw)
        if df is None or df.empty:
            raise RuntimeError("Yahoo Finance returned no data (possibly rate-limited)")
        return df
    return with_retries(go)


def frames(tickers, **kw):
    """One batched download, then a single individual retry for tickers that came back empty
    (Yahoo occasionally drops one symbol from a batch)."""
    df = _download(tickers, **kw)
    out = {t: split_frame(df, t) for t in tickers}
    for t in [t for t, f in out.items() if f is None]:
        try:
            out[t] = split_frame(_download([t], **kw), t)
        except Exception:  # noqa: BLE001
            out[t] = None
    return out


def split_frame(df, ticker):
    """Extract one ticker's OHLCV frame from a yf.download result."""
    if isinstance(df.columns, pd.MultiIndex):
        if ticker not in df.columns.get_level_values(0):
            return None
        sub = df[ticker]
    else:
        sub = df
    cols = [c for c in FIELDS if c in sub.columns]
    sub = sub[cols].dropna(subset=["Close"])
    if sub.empty:
        return None
    sub.index = pd.to_datetime(sub.index).tz_localize(None).normalize()
    return sub


def apply_currency(frame, currency):
    """London quotes come in pence (GBp): convert prices to GBP."""
    if currency == "GBp":
        frame = frame.copy()
        for c in PRICE_FIELDS:
            if c in frame.columns:
                frame[c] = frame[c] / 100.0
        return frame, "GBP"
    return frame, currency


def completed_bars(frame, exchange, now=None):
    """Drop today's bar if that exchange's session today has not closed yet."""
    now = now or datetime.now(timezone.utc)
    cal = xcals.get_calendar(exchange)
    local_today = pd.Timestamp(now).tz_convert(cal.tz).normalize().tz_localize(None)
    if len(frame) and frame.index[-1] >= local_today:
        if cal.is_session(local_today):
            close = cal.session_close(local_today)
            if pd.Timestamp(now) < close:
                frame = frame[frame.index < local_today]
        else:
            frame = frame[frame.index < local_today]
    return frame


def fetch_currencies(tickers):
    """Quote currency per ticker from Yahoo; falls back to the exchange's currency."""
    import yfinance as yf
    out = {}
    for t in tickers:
        info = config.BY_TICKER[t]
        cur = None
        try:
            cur = yf.Ticker(t).fast_info.get("currency")
        except Exception:  # noqa: BLE001
            cur = None
        if not cur:
            suffix = "." + t.split(".")[-1] if "." in t else ""
            cur = config.SUFFIX_CURRENCY.get(suffix, "USD" if info["region"] == "US" else None)
        if info["kind"] == "index":
            cur = None  # index points, no currency
        out[t] = cur
    return out


def fetch_history(tickers, currencies, now=None):
    """5-year daily history. Re-downloaded in full every day because adjusted
    closes are rescaled retroactively after each dividend or split."""
    got = frames(tickers, period=f"{config.HISTORY_YEARS}y", interval="1d")
    out = {}
    for t in tickers:
        frame = got[t]
        if frame is None:
            out[t] = {"status": "error", "error": "no data returned by Yahoo Finance for this ticker"}
            continue
        frame, cur = apply_currency(frame, currencies.get(t))
        frame = completed_bars(frame, config.BY_TICKER[t]["exchange"], now)
        out[t] = {
            "status": "ok", "currency": cur,
            "dates": [d.strftime("%Y-%m-%d") for d in frame.index],
            "open": frame["Open"].round(6).tolist(),
            "high": frame["High"].round(6).tolist(),
            "low": frame["Low"].round(6).tolist(),
            "close": frame["Close"].round(6).tolist(),
            "adj_close": frame["Adj Close"].round(6).tolist(),
            "volume": [None if pd.isna(v) else int(v) for v in frame["Volume"].tolist()],
        }
    return out


def fetch_quotes(tickers, currencies):
    """Latest delayed quote = last daily bar (today's bar is in progress during the session)."""
    got = frames(tickers, period="5d", interval="1d")
    fetched = store.now_iso()
    out = {}
    for t in tickers:
        frame = got[t]
        if frame is None or len(frame) < 1:
            out[t] = {"status": "error", "error": "no quote returned by Yahoo Finance", "fetched_at": fetched}
            continue
        frame, cur = apply_currency(frame, currencies.get(t))
        last = float(frame["Close"].iloc[-1])
        prev = float(frame["Close"].iloc[-2]) if len(frame) >= 2 else None
        out[t] = {
            "status": "ok", "fetched_at": fetched, "currency": cur,
            "date": frame.index[-1].strftime("%Y-%m-%d"),
            "last": last, "prev_close": prev,
            "change": (last - prev) if prev is not None else None,
            "pct": (last / prev - 1) if prev else None,
            "volume": None if pd.isna(frame["Volume"].iloc[-1]) else int(frame["Volume"].iloc[-1]),
        }
    return out
