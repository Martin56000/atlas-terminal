"""Entry point of the scheduled update job.

    python -m pipeline.run            # decide from the clock what to update
    python -m pipeline.run --force    # update everything now

Writes JSON files into site/data/. Never writes a number that did not come
from a source: failures are recorded as status=error with the message."""
import argparse
import os
import sys
import traceback
from datetime import datetime, timedelta

import pandas as pd

from . import config, metrics, schedule, store
from .market import safe_name

US_QUOTES = [t["ticker"] for t in config.US_WATCH + config.US_OVERVIEW_EXTRA] + ["BZ=F", "GC=F"]
EU_QUOTES = [t["ticker"] for t in config.EU_WATCH + config.EU_INDICES] + ["EURUSD=X"]
ALL = [t["ticker"] for t in config.UNIVERSE]


def log(msg):
    print(f"[{store.now_iso()}] {msg}", flush=True)


# ---------------------------------------------------------------- meta / currencies
def ensure_currencies(meta):
    from .market import fetch_currencies
    cur = meta.get("currencies") or {}
    stamp = meta.get("currencies_at")
    stale = not stamp or (schedule.utcnow() - datetime.fromisoformat(stamp)) > timedelta(days=7)
    missing = [t for t in ALL if t not in cur]
    if stale or missing:
        log("fetching quote currencies")
        cur = fetch_currencies(ALL)
        meta["currencies"], meta["currencies_at"] = cur, store.now_iso()
    return cur


# ---------------------------------------------------------------- tasks
def task_macro():
    from . import macro
    log("macro: FRED + ECB")
    data, errors = {}, {}
    for sid in config.FRED_SERIES:
        try:
            data[sid] = macro.fetch_fred(sid)
        except Exception as e:  # noqa: BLE001
            errors[sid] = f"{type(e).__name__}: {e}"
    for sid, fn in (("HICP_EA", macro.fetch_ecb_hicp), ("ECBDFR", macro.fetch_ecb_deposit_rate)):
        try:
            data[sid] = fn()
        except Exception as e:  # noqa: BLE001
            errors[sid] = f"{type(e).__name__}: {e}"[:400]
    if not data:
        raise RuntimeError("all macro series failed: " + "; ".join(f"{k}: {v}" for k, v in errors.items()))
    store.write("macro.json", store.envelope_ok("FRED (fred.stlouisfed.org) + ECB Data Portal", data, {"errors": errors}))


def task_quotes(tickers, region, currencies):
    from .market import fetch_quotes
    log(f"quotes {region}: {len(tickers)} tickers")
    prev = store.read("quotes.json") or {"_meta": {"source": "Yahoo Finance via yfinance (delayed)", "regions": {}}, "data": {}}
    regions = prev["_meta"].setdefault("regions", {})
    last_ok = (regions.get(region) or {}).get("last_success")
    try:
        q = fetch_quotes(tickers, currencies)
        prev["data"].update(q)
        regions[region] = {"fetched_at": store.now_iso(), "status": "ok", "error": None, "last_success": store.now_iso()}
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        err = f"{type(e).__name__}: {e}"[:500]
        for t in tickers:
            prev["data"][t] = {"status": "error", "error": err, "fetched_at": store.now_iso()}
        regions[region] = {"fetched_at": store.now_iso(), "status": "error", "error": err, "last_success": last_ok}
    store.write("quotes.json", prev)


def task_history(currencies):
    from .market import fetch_history
    log("history: 5y daily for all tickers")
    src = "Yahoo Finance via yfinance (daily, delayed)"
    try:
        hist = fetch_history(ALL, currencies)
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        for t in ALL:
            name = f"history/{safe_name(t)}.json"
            store.write(name, store.envelope_error(src, e, store.read(name)))
        return
    for t, h in hist.items():
        name = f"history/{safe_name(t)}.json"
        if h["status"] == "ok":
            h.pop("status")
            store.write(name, store.envelope_ok(src, h))
        else:
            store.write(name, store.envelope_error(src, RuntimeError(h["error"]), store.read(name)))


def _adj_series(ticker):
    env = store.read(f"history/{safe_name(ticker)}.json")
    if not env or env["_meta"]["status"] != "ok" or not env["data"]:
        return None
    d = env["data"]
    return pd.Series(d["adj_close"], index=pd.to_datetime(d["dates"]), dtype=float).dropna()


def task_risk():
    log("risk metrics")
    macro_env = store.read("macro.json") or {}
    mdata = (macro_env.get("data") or {})
    rf = {}
    for region, sid in config.RISK_FREE_SERIES.items():
        s = mdata.get(sid)
        rf[region] = {"series": sid, "value": s["latest"]["value"] / 100, "date": s["latest"]["date"]} if s else None

    bench = {r: _adj_series(t) for r, t in config.BENCHMARK.items()}
    out, returns = {}, {}
    for t in config.WATCHLIST_UNIVERSE:
        info = config.BY_TICKER[t]
        p = _adj_series(t)
        b = bench[info["region"]]
        r_free = rf[info["region"]]
        if p is None or len(p) < 3:
            out[t] = {"status": "error", "error": "price history unavailable"}
            continue
        if b is None:
            out[t] = {"status": "error", "error": f"benchmark {config.BENCHMARK[info['region']]} history unavailable"}
            continue
        m = metrics.risk_metrics(p, b, r_free["value"] if r_free else None, config.RISK_WINDOW)
        m.update({"status": "ok", "benchmark": config.BENCHMARK[info["region"]],
                  "rf_series": r_free["series"] if r_free else None, "rf_date": r_free["date"] if r_free else None})
        if r_free is None:
            m["sharpe_note"] = "risk-free rate unavailable"
        out[t] = m
        r = metrics.log_returns(metrics.window_prices(p, config.RISK_WINDOW))
        returns[t] = {"dates": [d.strftime("%Y-%m-%d") for d in r.index], "r": [round(x, 8) for x in r.tolist()]}
    store.write("risk.json", store.envelope_ok("Computed from Yahoo Finance adjusted closes; rf from FRED",
                                               {"window": config.RISK_WINDOW, "rf": rf, "metrics": out, "returns": returns}))


def task_fundamentals():
    from . import fundamentals as fa
    log("fundamentals: SEC EDGAR")
    src = "SEC EDGAR (data.sec.gov companyfacts + submissions)"
    need_sec = []
    for t in config.WATCHLIST_UNIVERSE:  # ETFs and companies without a free source need no request
        info = config.BY_TICKER[t]
        if info["kind"] == "etf" or (info["region"] == "EU" and not info.get("adr")):
            reason = "etf" if info["kind"] == "etf" else "no_free_source"
            store.write(f"fundamentals/{safe_name(t)}.json", store.envelope_ok(src, {"kind": "na", "reason": reason}))
        else:
            need_sec.append(t)
    try:
        client = fa.SecClient()
        ciks = fa.cik_map(client)
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        for t in need_sec:
            name = f"fundamentals/{safe_name(t)}.json"
            store.write(name, store.envelope_error(src, e, store.read(name)))
        return
    for t in need_sec:
        name = f"fundamentals/{safe_name(t)}.json"
        store.run_dataset(name, src, lambda t=t: fa.fetch_company(client, t, ciks))


def task_news():
    from . import news, sentiment
    log("news + sentiment")
    cache = store.read("sentiment_cache.json") or {}
    per, all_items = {}, []
    for t in config.WATCHLIST_UNIVERSE:
        try:
            res = news.fetch_for_ticker(t)
            per[t] = res
            all_items += res["en"]
        except Exception as e:  # noqa: BLE001
            per[t] = {"en": [], "fr": None, "errors": [f"{type(e).__name__}: {e}"]}
    sentiment_error = None
    try:
        sentiment.score_new(all_items, cache)
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        sentiment_error = f"{type(e).__name__}: {e}"[:300]
    live_links = set()
    data = {}
    for t, res in per.items():
        en = sentiment.attach(res["en"], cache)
        fr = sentiment.attach(res["fr"], cache) if res["fr"] is not None else None
        live_links.update(h["link"] for h in en)
        failed = not en and not fr and res["errors"]
        data[t] = {"status": "error" if failed else "ok", "errors": res["errors"],
                   "en": en, "fr": fr, "avg": sentiment.average(en)}
    store.write("sentiment_cache.json", {k: v for k, v in cache.items() if k in live_links})
    store.write("news.json", store.envelope_ok("Yahoo Finance news + Google News RSS; sentiment: ProsusAI/finbert",
                                               data, {"sentiment_error": sentiment_error}))


def task_validate():
    from . import validate
    log("cross-check AAPL / MC.PA")
    store.run_dataset("validation.json", "Independent recomputation from yfinance", validate.run)


# ---------------------------------------------------------------- main
def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="run every task now")
    ap.add_argument("--only", help="comma-separated task list (daily,quotes_us,quotes_eu,eu_close,news)")
    args = ap.parse_args(argv)

    now = schedule.utcnow()
    state = store.read("state.json") or {}
    tasks = args.only.split(",") if args.only else schedule.decide(now, state, force=args.force)
    log(f"tasks: {tasks or 'nothing to do'}")
    gh_out = os.environ.get("GITHUB_OUTPUT")
    if gh_out:
        with open(gh_out, "a", encoding="utf-8") as f:
            f.write(f"ran={'true' if tasks else 'false'}\n")
    if not tasks:
        return 0

    meta = store.read("meta.json") or {}
    try:
        currencies = ensure_currencies(meta)
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        currencies = meta.get("currencies") or {}

    today = now.astimezone(schedule.PARIS).date().isoformat()
    paris_t = now.astimezone(schedule.PARIS).time()
    if "daily" in tasks:
        _safe(task_macro, "macro.json", "FRED (fred.stlouisfed.org) + ECB Data Portal")
        task_history(currencies)
        task_quotes(US_QUOTES, "US", currencies)
        task_quotes(EU_QUOTES, "EU", currencies)
        task_risk()
        task_fundamentals()
        if "news" not in tasks:
            task_news()
            state["news_at"] = store.now_iso()
        task_validate()
        state["daily"] = today
        if paris_t >= schedule._hm(config.EU_CLOSE_RUN_AT):
            state["eu_close"] = today
    if "eu_close" in tasks:
        task_history(currencies)
        task_quotes(EU_QUOTES, "EU", currencies)
        task_risk()
        state["eu_close"] = today
    if "quotes_us" in tasks and "daily" not in tasks:
        task_quotes(US_QUOTES, "US", currencies)
    if "quotes_eu" in tasks and "daily" not in tasks and "eu_close" not in tasks:
        task_quotes(EU_QUOTES, "EU", currencies)
    if "news" in tasks:
        task_news()
        state["news_at"] = store.now_iso()

    meta.update({
        "generated_at": store.now_iso(),
        "last_tasks": tasks,
        "sessions": schedule.sessions_json(now),
        "universe": config.UNIVERSE,
        "watchlist_universe": config.WATCHLIST_UNIVERSE,
        "default_watchlist": config.DEFAULT_WATCHLIST,
        "benchmark": config.BENCHMARK,
    })
    store.write("meta.json", meta)
    store.write("state.json", state)
    log("done")
    return 0


def _safe(fn, name, source):
    try:
        fn()
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        store.write(name, store.envelope_error(source, e, store.read(name)))


if __name__ == "__main__":
    sys.exit(main())
