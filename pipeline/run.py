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
EU_QUOTES = [t["ticker"] for t in config.EU_STOCKS + config.EU_INDICES + config.WORLD_INDICES + config.FX_COMMOD if t["region"] == "EU"]
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
    log("macro: FRED (fallback Treasury / NY Fed / BLS) + ECB")
    data, errors = {}, {}
    fred_down = None
    try:  # quick probe: FRED often hangs for cloud IPs; don't spend 15 minutes discovering it
        data["DFF"] = macro.fetch_fred("DFF", attempts=1, timeout=25)
    except Exception as e:  # noqa: BLE001
        fred_down = f"{type(e).__name__}: {e}"[:200]
    if not fred_down:
        for sid in [s for s in config.FRED_SERIES if s != "DFF"]:
            try:
                data[sid] = macro.fetch_fred(sid)
            except Exception as e:  # noqa: BLE001
                errors[sid] = f"FRED: {type(e).__name__}: {e}"[:300]
    missing = [s for s in config.FRED_SERIES if s not in data]
    today = schedule.utcnow().date()
    start_year = today.year - 9  # BLS v1 allows 10 years per request
    if "DFF" in missing:
        try:
            data["DFF"] = macro.fetch_effr(f"{start_year}-01-01", today.isoformat())
        except Exception as e:  # noqa: BLE001
            errors["DFF"] = f"FRED: {fred_down} | NY Fed: {type(e).__name__}: {e}"[:400]
    if any(s in missing for s in macro.TREASURY_COLS):
        try:
            for sid, ser in macro.fetch_treasury(start_year, today.year).items():
                if sid in missing:
                    data[sid] = ser
        except Exception as e:  # noqa: BLE001
            for sid in macro.TREASURY_COLS:
                if sid in missing:
                    errors[sid] = f"FRED: {fred_down or errors.get(sid)} | Treasury: {type(e).__name__}: {e}"[:400]
    bls_needed = [s for s in config.BLS_SERIES if s in missing]
    if bls_needed:
        try:
            got = macro.fetch_bls([config.BLS_SERIES[s] for s in bls_needed], start_year, today.year)
            for s in bls_needed:
                pts = got[config.BLS_SERIES[s]]
                data[s] = macro._series(pts, f"BLS {config.BLS_SERIES[s]}")
                if s == "CPIAUCSL":
                    data[s]["yoy"] = macro._series(macro.yoy(pts), f"BLS {config.BLS_SERIES[s]}, computed YoY")
        except Exception as e:  # noqa: BLE001
            for s in bls_needed:
                errors[s] = f"FRED: {fred_down or errors.get(s)} | BLS: {type(e).__name__}: {e}"[:400]
    for s in data:
        errors.pop(s, None)
    for sid, fn in (("HICP_EA", macro.fetch_ecb_hicp), ("ECBDFR", macro.fetch_ecb_deposit_rate)):
        try:
            data[sid] = fn()
        except Exception as e:  # noqa: BLE001
            errors[sid] = f"{type(e).__name__}: {e}"[:400]
    if not data:
        raise RuntimeError("all macro series failed: " + "; ".join(f"{k}: {v}" for k, v in errors.items()))
    providers = ["FRED", "ECB", "BLS", "US Treasury", "Federal Reserve Bank of New York"]
    sources = sorted({next((p for p in providers if v.get("source", "").startswith(p)), v.get("source", "?")) for v in data.values()})
    store.write("macro.json", store.envelope_ok(" + ".join(sources), data, {"errors": errors, "fred_down": fred_down}))


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

    bench = {t: _adj_series(t) for t in set(config.BENCHMARK.values())}
    out, returns = {}, {}
    for t in config.WATCHLIST_UNIVERSE:
        info = config.BY_TICKER[t]
        p = _adj_series(t)
        bname = config.benchmark_for(info)
        b = bench[bname]
        r_free = rf[info["region"]]
        if p is None or len(p) < 3:
            out[t] = {"status": "error", "error": "price history unavailable"}
            continue
        if b is None:
            out[t] = {"status": "error", "error": f"benchmark {bname} history unavailable"}
            continue
        m = metrics.risk_metrics(p, b, r_free["value"] if r_free else None, config.RISK_WINDOW)
        m.update({"status": "ok", "benchmark": bname,
                  "rf_series": r_free["series"] if r_free else None, "rf_date": r_free["date"] if r_free else None})
        if r_free is None:
            m["sharpe_note"] = "risk-free rate unavailable"
        out[t] = m
        r = metrics.log_returns(metrics.window_prices(p, config.RISK_WINDOW))
        returns[t] = {"dates": [d.strftime("%Y-%m-%d") for d in r.index], "r": [round(x, 6) for x in r.tolist()]}
    store.write("risk.json", store.envelope_ok("Computed from Yahoo Finance adjusted closes; rf: 3-month US Treasury (US), ECB deposit rate (EU)",
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


def task_news(tickers=None):
    """Refresh news for `tickers` (default: all) and merge with the other tickers' last results."""
    from . import news, sentiment, translate
    tickers = tickers or config.WATCHLIST_UNIVERSE
    log(f"news + sentiment: {len(tickers)} tickers")
    cache = store.read("sentiment_cache.json") or {}
    prev = store.read("news.json") or {}
    data = {t: v for t, v in (prev.get("data") or {}).items() if t in config.WATCHLIST_UNIVERSE and t not in tickers}
    per, all_items = {}, []
    import time
    for t in tickers:
        time.sleep(0.25)   # be gentle with Google News
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
    tcache = store.read("translation_cache_tcbig.json") or {}
    translation_error = None
    try:
        translate.translate_new(all_items, tcache, budget_s=config.TRANSLATE_BUDGET_S)
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        translation_error = f"{type(e).__name__}: {e}"[:300]
    fetched = store.now_iso()
    for t, res in per.items():
        en = translate.attach(sentiment.attach(res["en"], cache), tcache)
        fr = sentiment.attach(res["fr"], cache) if res["fr"] is not None else None
        failed = not en and not fr and res["errors"]
        data[t] = {"status": "error" if failed else "ok", "errors": res["errors"], "fetched_at": fetched,
                   "en": en, "fr": fr, "avg": sentiment.average(en)}
    live_links = {h["link"] for v in data.values() for h in (v.get("en") or [])}
    store.write("sentiment_cache.json", {k: v for k, v in cache.items() if k in live_links})
    store.write("translation_cache_tcbig.json", {k: v for k, v in tcache.items() if k in live_links})
    store.write("news.json", store.envelope_ok(
        "Yahoo Finance news + Google News RSS; sentiment: ProsusAI/finbert; translation: Helsinki-NLP/opus-mt-tc-big-en-fr",
        data, {"sentiment_error": sentiment_error, "translation_error": translation_error}))


def _age_hours(env):
    ts = ((env or {}).get("_meta") or {}).get("fetched_at")
    if not ts:
        return None
    return (schedule.utcnow() - datetime.fromisoformat(ts)).total_seconds() / 3600


def rotation(prefix, tickers, n, max_age_h, error_age_h=24):
    """Never-fetched first (universe order), then the oldest beyond their age limit
    (failed fetches are retried after error_age_h, successful ones after max_age_h)."""
    never, old = [], []
    for t in tickers:
        env = store.read(f"{prefix}/{safe_name(t)}.json")
        age = _age_hours(env)
        limit = error_age_h if (env or {}).get("_meta", {}).get("status") == "error" else max_age_h
        if age is None:
            never.append(t)
        elif age >= limit:
            old.append((-age, t))
    return (never + [t for _, t in sorted(old)])[:n]


def task_company():
    import time
    from . import company
    stocks = [t for t in config.WATCHLIST_UNIVERSE if config.BY_TICKER[t]["kind"] == "stock"]
    todo = rotation("company", stocks, config.COMPANY_PER_RUN, config.COMPANY_MAX_AGE_H)
    log(f"company pages (Yahoo): {len(todo)} of {len(stocks)}")
    src = "Yahoo Finance via yfinance (profile, statements, analyst estimates)"
    for t in todo:
        prev_pf = (((store.read(f"company/{safe_name(t)}.json") or {}).get("data") or {}).get("profile") or {})

        def fetch_keep(t=t, prev_pf=prev_pf):
            d = company.fetch(t)
            if prev_pf.get("summary_fr") and prev_pf.get("summary") == d["profile"].get("summary"):
                d["profile"]["summary_fr"] = prev_pf["summary_fr"]
            return d
        store.run_dataset(f"company/{safe_name(t)}.json", src, fetch_keep)
        time.sleep(0.3)


def task_translate_profiles(budget_s=360):
    """Machine-translate company descriptions once (kept in the company page), newest pages first."""
    import time
    from . import translate
    start, done = time.monotonic(), 0
    for t in config.WATCHLIST_UNIVERSE:
        if time.monotonic() - start > budget_s:
            break
        name = f"company/{safe_name(t)}.json"
        env = store.read(name)
        if not env or env["_meta"]["status"] != "ok":
            continue
        pf = env["data"].get("profile") or {}
        if not pf.get("summary") or pf.get("summary_fr"):
            continue
        try:
            pf["summary_fr"] = translate.translate_text(pf["summary"], max_sentences=3)
            pf["summary_fr_excerpt"] = len(translate.split_sentences(pf["summary"])) > 3
            store.write(name, env)
            done += 1
        except Exception:  # noqa: BLE001
            traceback.print_exc()
            break
    log(f"profile translations: {done}")


def task_esef():
    from . import esef
    eu = [u["ticker"] for u in config.EU_STOCKS]
    todo = rotation("esef", eu, config.ESEF_PER_RUN, config.ESEF_MAX_AGE_DAYS * 24)
    log(f"ESEF annual reports: {len(todo)} of {len(eu)}")
    src = "ESEF annual report (filings.xbrl.org)"
    for t in todo:
        name = f"esef/{safe_name(t)}.json"
        prev = (store.read(name) or {}).get("data") or {}
        ov = config.ESEF_OVERRIDES.get(t, {})
        store.run_dataset(name, src, lambda t=t, prev=prev, ov=ov: esef.fetch(
            config.BY_TICKER[t], known_lei=ov.get("lei") or prev.get("lei"), search=ov.get("search")))


def task_companies_index():
    """One small file for EQS / COMPS / earnings calendar: multiples in EUR, size class, next results."""
    from . import comps, fx
    from .company import facts
    quotes = (store.read("quotes.json") or {}).get("data") or {}
    rates = fx.rates_from_quotes(quotes)
    today = schedule.utcnow().date().isoformat()
    rows = {}
    for t in config.WATCHLIST_UNIVERSE:
        if config.BY_TICKER[t]["kind"] != "stock":
            continue
        env = store.read(f"company/{safe_name(t)}.json")
        if not env or env["_meta"]["status"] != "ok":
            rows[t] = {"status": "error", "error": (env or {}).get("_meta", {}).get("error") or "not fetched yet"}
            continue
        c = env["data"]
        q = quotes.get(t) or {}
        r = comps.comp_row(c, q, rates)
        upcoming = [d for d in (c.get("calendar") or {}).get("earnings_dates") or [] if d >= today]
        tg = c.get("targets") or {}
        r.update({"status": "ok", "fetched_at": env["_meta"]["fetched_at"], "next_earnings": upcoming[0] if upcoming else None,
                  "eps_estimate_next": (c.get("calendar") or {}).get("eps_avg"), "target_mean": tg.get("mean"),
                  "n_analysts": tg.get("n_analysts"), "reco_key": tg.get("reco_key"),
                  "facts": facts(c, q.get("last") if q.get("status") == "ok" else None)})
        rows[t] = r
    ok_rows = {k: v for k, v in rows.items() if v.get("status") == "ok"}
    store.write("companies.json", store.envelope_ok(
        "Yahoo Finance (company data) + our calculations (EUR via Yahoo FX quotes)",
        {"rows": rows, "sector_medians": comps.sector_medians(ok_rows), "fx": rates,
         "size_thresholds_eur": {"large": comps.SIZE_LARGE, "mid": comps.SIZE_MID}}))


def task_deals():
    from . import deals
    sec = []
    for t in config.WATCHLIST_UNIVERSE:
        env = store.read(f"fundamentals/{safe_name(t)}.json")
        d = ((env or {}).get("data") or {})
        for f in d.get("deals") or []:
            sec.append({"ticker": t, **f})
    sec.sort(key=lambda f: f["filed"], reverse=True)
    news = (store.read("news.json") or {}).get("data") or {}
    store.write("deals.json", store.envelope_ok("SEC EDGAR filings + keyword detection on collected headlines",
                                                {"sec": sec[:200], "news": deals.news_deals(news)}))


def task_perf():
    """1W / 1M / 3M / YTD / 1Y performance and 52-week range for every ticker (WEI, MOST, EQS)."""
    out = {}
    for u in config.UNIVERSE:
        env = store.read(f"history/{safe_name(u['ticker'])}.json")
        d = (env or {}).get("data")
        if not d or (env["_meta"].get("status") != "ok"):
            continue
        closes = d["adj_close"] if u["kind"] == "stock" else d["close"]
        pts = [(dt, c) for dt, c in zip(d["dates"], closes) if c is not None]
        out[u["ticker"]] = metrics.perf_stats([p[0] for p in pts], [p[1] for p in pts])
    store.write("perf.json", store.envelope_ok("Computed from Yahoo Finance daily closes (adjusted for stocks)", out))


def task_intraday(tickers, currencies):
    from .market import fetch_intraday
    todo = [t for t in tickers if t in config.INTRADAY]
    if not todo:
        return
    prev = (store.read("intraday.json") or {}).get("data") or {}
    try:
        prev.update(fetch_intraday(todo, currencies))
        store.write("intraday.json", store.envelope_ok("Yahoo Finance 5-minute bars via yfinance (delayed)", prev))
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        store.write("intraday.json", store.envelope_error("Yahoo Finance 5-minute bars", e, store.read("intraday.json")))


def track_failures(state):
    """Remember since when each ticker / macro series has been failing (STATUS tab, alerts)."""
    from .health import update_fail_since
    now = store.now_iso()
    for t, q in ((store.read("quotes.json") or {}).get("data") or {}).items():
        if t in config.BY_TICKER:
            update_fail_since(state, t, q.get("status") != "ok", q.get("error"), now)
    for t in list((state.get("fail_since") or {})):
        if t not in config.BY_TICKER and not t.startswith("macro:"):
            state["fail_since"].pop(t)            # ticker removed from the universe
    menv = store.read("macro.json") or {}
    errs = (menv.get("_meta") or {}).get("errors") or {}
    for sid in config.FRED_SERIES + ["HICP_EA", "ECBDFR"]:
        update_fail_since(state, "macro:" + sid, sid in errs, errs.get(sid), now)


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
        _safe(task_macro, "macro.json", "FRED / US Treasury / NY Fed / BLS / ECB")
        task_history(currencies)
        task_quotes(US_QUOTES, "US", currencies)
        task_quotes(EU_QUOTES, "EU", currencies)
        task_risk()
        task_fundamentals()
        task_validate()
        state["daily"] = today
        if paris_t >= schedule._hm(config.EU_CLOSE_RUN_AT):
            state["eu_close"] = today
    if "eu_close" in tasks:
        task_history(currencies)
        task_quotes(EU_QUOTES, "EU", currencies)
        task_risk()
        state["eu_close"] = today
    if "daily" in tasks or "eu_close" in tasks:
        _safe(task_perf, "perf.json", "daily closes")
    if "quotes_us" in tasks and "daily" not in tasks:
        task_quotes(US_QUOTES, "US", currencies)
    if "quotes_eu" in tasks and "daily" not in tasks and "eu_close" not in tasks:
        task_quotes(EU_QUOTES, "EU", currencies)
    if "quotes_us" in tasks or "daily" in tasks:
        task_intraday(US_QUOTES, currencies)
    if "quotes_eu" in tasks or "daily" in tasks or "eu_close" in tasks:
        task_intraday(EU_QUOTES, currencies)
    heavy = "daily" in tasks or "eu_close" in tasks
    if heavy:
        _safe(task_company, "company_task_error.json", "company pages")
        _safe(task_esef, "esef_task_error.json", "ESEF")
        _safe(task_translate_profiles, "translate_task_error.json", "profile translation")
    if "daily" in tasks or "eu_close" in tasks:      # all tickers, small & mid caps included
        task_news()
        state["news_at"] = store.now_iso()
    elif "news" in tasks:                            # hourly: large caps only
        task_news(config.NEWS_HOURLY)
        state["news_at"] = store.now_iso()

    _safe(task_companies_index, "companies.json", "Yahoo Finance (company data)")
    _safe(task_deals, "deals.json", "SEC EDGAR + headlines")
    if gh_out:
        with open(gh_out, "a", encoding="utf-8") as f:
            f.write(f"heavy={'true' if heavy else 'false'}\n")

    meta.update({
        "generated_at": store.now_iso(),
        "last_tasks": tasks,
        "sessions": schedule.sessions_json(now),
        "universe": config.UNIVERSE,
        "watchlist_universe": config.WATCHLIST_UNIVERSE,
        "default_watchlist": config.DEFAULT_WATCHLIST,
        "benchmark": config.BENCHMARK,
        "esef_countries": sorted(__import__("pipeline.esef", fromlist=["x"]).ESEF_COUNTRIES),
    })
    track_failures(state)
    store.write("meta.json", meta)
    store.write("state.json", state)
    from . import health
    store.write("status.json", health.compute())
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
