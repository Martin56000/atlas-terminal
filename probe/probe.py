"""Check candidate tickers against Yahoo Finance (run on GitHub Actions, where Yahoo is reachable).
Writes probe/result.json: for each candidate, ok/failed, Yahoo's name, currency, exchange, market cap,
last close date; for failures, Yahoo search suggestions. Nothing here is shown on the site."""
import json
import re
import sys
import time

import yfinance as yf

lines = [l.strip() for l in open("probe/candidates.txt", encoding="utf-8")]
cands, section = [], None
for l in lines:
    if l.startswith("## "):
        section = l[3:].split()
    elif l and not l.startswith("#"):
        t, n = l.split("|", 1)
        cands.append({"ticker": t.strip(), "name": n.strip(), "country": section[0], "mic": section[1]})

tickers = [c["ticker"] for c in cands]
df = yf.download(tickers, period="1mo", interval="1d", group_by="ticker", auto_adjust=False,
                 progress=False, threads=True)
out = []
for c in cands:
    t = c["ticker"]
    r = dict(c)
    try:
        sub = df[t].dropna(subset=["Close"])
    except Exception:  # noqa: BLE001
        sub = None
    r["ok"] = sub is not None and len(sub) >= 5
    r["last_date"] = sub.index[-1].strftime("%Y-%m-%d") if r["ok"] else None
    r["last_close"] = float(sub["Close"].iloc[-1]) if r["ok"] else None
    if r["ok"] and not t.endswith("=X"):
        try:
            tk = yf.Ticker(t)
            fi = tk.fast_info
            r["currency"] = fi.get("currency")
            r["market_cap"] = fi.get("marketCap")
            r["exchange"] = fi.get("exchange")
            md = tk.history_metadata or {}
            r["yahoo_name"] = md.get("longName") or md.get("shortName")
        except Exception as e:  # noqa: BLE001
            r["meta_error"] = str(e)[:120]
        time.sleep(0.2)
    else:
        try:
            q = yf.Search(re.sub(r"\(.*?\)", "", c["name"]), max_results=8).quotes
            r["suggest"] = [{"symbol": x.get("symbol"), "name": x.get("longname") or x.get("shortname"),
                             "exch": x.get("exchange"), "type": x.get("quoteType")} for x in q]
        except Exception as e:  # noqa: BLE001
            r["suggest_error"] = str(e)[:120]
        time.sleep(0.5)
    out.append(r)
json.dump(out, open("probe/result.json", "w"), ensure_ascii=False, indent=1)
print(sum(r["ok"] for r in out), "/", len(out), "ok")
