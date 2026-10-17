"""Company page (DES): profile, results, analyst consensus, price targets, recommendations,
earnings surprises and the next earnings date, from Yahoo Finance via yfinance.

Everything here is either a Yahoo value (labelled as such) or a simple calculation on those values
(growth, margins, net debt). Analyst estimates are shown as analyst estimates, never as our forecast."""
from datetime import date, datetime, timezone

MODULES = ["assetProfile", "price", "summaryDetail", "defaultKeyStatistics", "financialData",
           "calendarEvents", "earningsTrend", "earningsHistory", "recommendationTrend"]

INCOME_ROWS = {"revenue": ["TotalRevenue", "OperatingRevenue"], "gross_profit": ["GrossProfit"],
               "ebit": ["OperatingIncome", "EBIT"], "ebitda": ["EBITDA", "NormalizedEBITDA"],
               "net_income": ["NetIncomeCommonStockholders", "NetIncome"], "eps_diluted": ["DilutedEPS"]}
BALANCE_ROWS = {"total_debt": ["TotalDebt"], "cash": ["CashAndCashEquivalents", "CashCashEquivalentsAndShortTermInvestments"],
                "equity": ["StockholdersEquity", "CommonStockEquity"], "net_debt_reported": ["NetDebt"],
                "shares": ["OrdinarySharesNumber", "ShareIssued"]}
CASHFLOW_ROWS = {"op_cash_flow": ["OperatingCashFlow"], "capex": ["CapitalExpenditure"], "fcf": ["FreeCashFlow"]}


# ---------------- small helpers ---------------------------------------------------------------
def raw(v):
    """quoteSummary values are plain numbers or {'raw': x, 'fmt': '...'}; {} means missing."""
    if isinstance(v, dict):
        return v.get("raw") if "raw" in v else None
    return v


def as_date(v):
    v = raw(v) if isinstance(v, dict) and "raw" in v else v
    if isinstance(v, dict):
        v = v.get("fmt")
    if isinstance(v, (int, float)):
        return datetime.fromtimestamp(v, tz=timezone.utc).date().isoformat()
    if isinstance(v, str) and len(v) >= 10:
        return v[:10]
    return None


def ratio(a, b):
    return a / b if (a is not None and b not in (None, 0)) else None


def growth(cur, prev):
    return cur / prev - 1 if (cur is not None and prev not in (None, 0) and prev > 0) else None


# ---------------- quoteSummary parsing ----------------------------------------------------------
def parse_summary(js):
    res = (js or {}).get("quoteSummary", {}).get("result") or []
    if not res:
        err = (js or {}).get("quoteSummary", {}).get("error")
        raise ValueError(f"Yahoo quoteSummary returned no result ({err})")
    r = res[0]
    ap, pr, sd = r.get("assetProfile") or {}, r.get("price") or {}, r.get("summaryDetail") or {}
    ks, fd, ce = r.get("defaultKeyStatistics") or {}, r.get("financialData") or {}, r.get("calendarEvents") or {}

    profile = {
        "name": pr.get("longName") or pr.get("shortName"), "sector": ap.get("sector"), "industry": ap.get("industry"),
        "country": ap.get("country"), "city": ap.get("city"), "website": ap.get("website"),
        "employees": raw(ap.get("fullTimeEmployees")), "summary": ap.get("longBusinessSummary"),
        "exchange": pr.get("exchangeName"), "currency": pr.get("currency"),
        "financial_currency": fd.get("financialCurrency"),
    }
    valuation = {  # Yahoo's own computations, labelled as such on the site
        "market_cap_yahoo": raw(pr.get("marketCap")) or raw(sd.get("marketCap")),
        "shares_outstanding": raw(ks.get("sharesOutstanding")),
        "trailing_pe": raw(sd.get("trailingPE")), "forward_pe": raw(sd.get("forwardPE")),
        "price_to_book": raw(ks.get("priceToBook")), "ev_to_ebitda": raw(ks.get("enterpriseToEbitda")),
        "ev_to_revenue": raw(ks.get("enterpriseToRevenue")), "dividend_yield": raw(sd.get("dividendYield")),
        "payout_ratio": raw(sd.get("payoutRatio")), "beta_yahoo": raw(sd.get("beta")),
    }
    targets = {
        "current_price": raw(fd.get("currentPrice")), "mean": raw(fd.get("targetMeanPrice")),
        "median": raw(fd.get("targetMedianPrice")), "high": raw(fd.get("targetHighPrice")),
        "low": raw(fd.get("targetLowPrice")), "n_analysts": raw(fd.get("numberOfAnalystOpinions")),
        "reco_mean": raw(fd.get("recommendationMean")), "reco_key": fd.get("recommendationKey"),
    }
    earn = ce.get("earnings") or {}
    dates = [as_date(d) for d in (earn.get("earningsDate") or [])]
    calendar = {
        "earnings_dates": [d for d in dates if d], "eps_avg": raw(earn.get("earningsAverage")),
        "eps_low": raw(earn.get("earningsLow")), "eps_high": raw(earn.get("earningsHigh")),
        "revenue_avg": raw(earn.get("revenueAverage")), "ex_dividend": as_date(ce.get("exDividendDate")),
        "dividend_date": as_date(ce.get("dividendDate")),
    }
    estimates = []
    for tr in (r.get("earningsTrend") or {}).get("trend") or []:
        ee, re_, et = tr.get("earningsEstimate") or {}, tr.get("revenueEstimate") or {}, tr.get("epsTrend") or {}
        estimates.append({
            "period": tr.get("period"), "end_date": tr.get("endDate"),
            "eps_avg": raw(ee.get("avg")), "eps_low": raw(ee.get("low")), "eps_high": raw(ee.get("high")),
            "eps_year_ago": raw(ee.get("yearAgoEps")), "eps_n": raw(ee.get("numberOfAnalysts")), "eps_growth": raw(ee.get("growth")),
            "rev_avg": raw(re_.get("avg")), "rev_low": raw(re_.get("low")), "rev_high": raw(re_.get("high")),
            "rev_year_ago": raw(re_.get("yearAgoRevenue")), "rev_n": raw(re_.get("numberOfAnalysts")), "rev_growth": raw(re_.get("growth")),
            "eps_trend_now": raw(et.get("current")), "eps_trend_30d": raw(et.get("30daysAgo")), "eps_trend_90d": raw(et.get("90daysAgo")),
        })
    surprises = []
    for h in (r.get("earningsHistory") or {}).get("history") or []:
        surprises.append({"quarter": as_date(h.get("quarter")), "eps_actual": raw(h.get("epsActual")),
                          "eps_estimate": raw(h.get("epsEstimate")), "surprise_pct": raw(h.get("surprisePercent"))})
    surprises = [s for s in surprises if s["eps_actual"] is not None or s["eps_estimate"] is not None]
    surprises.sort(key=lambda s: s["quarter"] or "")
    recos = []
    for t in (r.get("recommendationTrend") or {}).get("trend") or []:
        recos.append({k: raw(t.get(k)) for k in ("strongBuy", "buy", "hold", "sell", "strongSell")} | {"period": t.get("period")})
    return {"profile": profile, "valuation": valuation, "targets": targets, "calendar": calendar,
            "estimates": [e for e in estimates if any(v is not None for k, v in e.items() if k not in ("period", "end_date"))],
            "surprises": surprises, "recommendations": recos}


# ---------------- statements ------------------------------------------------------------------
def _pick(df, names, col):
    import math
    for n in names:
        if df is not None and n in df.index:
            v = df.loc[n, col]
            try:
                v = float(v)
            except (TypeError, ValueError):
                continue
            if not math.isnan(v):
                return v
    return None


def statement_rows(df, rows, n):
    """DataFrame (rows = items, columns = period end dates) -> last n periods, oldest first."""
    if df is None or getattr(df, "empty", True):
        return []
    cols = sorted(df.columns)[-n:]
    out = []
    for c in cols:
        rec = {"end": str(c)[:10]}
        for key, names in rows.items():
            rec[key] = _pick(df, names, c)
        if any(v is not None for k, v in rec.items() if k != "end"):
            out.append(rec)
    return out


def enrich_annual(income, balance, cashflow):
    """Merge statements by period end and add simple derived ratios (growth, margins, net debt, ROE)."""
    bal = {r["end"]: r for r in balance}
    cf = {r["end"]: r for r in cashflow}
    out, prev = [], None
    for r in income:
        x = dict(r)
        x.update({k: v for k, v in bal.get(r["end"], {}).items() if k != "end"})
        x.update({k: v for k, v in cf.get(r["end"], {}).items() if k != "end"})
        if x.get("fcf") is None and x.get("op_cash_flow") is not None and x.get("capex") is not None:
            x["fcf"] = x["op_cash_flow"] + x["capex"]          # capex is reported negative
        nd = x.get("net_debt_reported")
        if nd is None and x.get("total_debt") is not None and x.get("cash") is not None:
            nd = x["total_debt"] - x["cash"]
        x["net_debt"] = nd
        x["gross_margin"] = ratio(x.get("gross_profit"), x.get("revenue"))
        x["ebit_margin"] = ratio(x.get("ebit"), x.get("revenue"))
        x["net_margin"] = ratio(x.get("net_income"), x.get("revenue"))
        x["roe"] = ratio(x.get("net_income"), x.get("equity"))
        x["net_debt_to_ebitda"] = ratio(nd, x.get("ebitda")) if (x.get("ebitda") or 0) > 0 else None
        x["revenue_growth"] = growth(x.get("revenue"), prev.get("revenue")) if prev else None
        out.append(x)
        prev = x
    return out


def yoy_quarter(quarters):
    """Last quarter vs the same quarter one year earlier (needs a period 350-380 days before)."""
    if len(quarters) < 2:
        return None
    last = quarters[-1]
    d_last = date.fromisoformat(last["end"])
    for q in quarters[:-1]:
        if 350 <= (d_last - date.fromisoformat(q["end"])).days <= 380:
            return {"end": last["end"], "prev_end": q["end"], "revenue_growth": growth(last.get("revenue"), q.get("revenue")),
                    "net_income": last.get("net_income"), "net_income_prev": q.get("net_income")}
    return None


# ---------------- factual commentary ----------------------------------------------------------
def facts(c, last_price=None, today=None):
    """Structured facts; the site turns them into sentences (FR/EN). Only produced when inputs exist."""
    out = []
    annual = c.get("annual") or []
    if len(annual) >= 2 and annual[-1].get("revenue_growth") is not None:
        out.append({"key": "rev_growth_fy", "v": annual[-1]["revenue_growth"], "fy": annual[-1]["end"]})
    if len(annual) >= 2 and annual[-1].get("net_margin") is not None and annual[-2].get("net_margin") is not None:
        out.append({"key": "net_margin_fy", "v": annual[-1]["net_margin"],
                    "delta_pts": (annual[-1]["net_margin"] - annual[-2]["net_margin"]) * 100, "fy": annual[-1]["end"]})
    q = yoy_quarter(c.get("quarterly") or [])
    if q and q["revenue_growth"] is not None:
        out.append({"key": "rev_growth_q", "v": q["revenue_growth"], "q": q["end"]})
    s = [x for x in (c.get("surprises") or []) if x.get("eps_actual") is not None and x.get("eps_estimate") is not None][-4:]
    if s:
        beats = sum(1 for x in s if x["eps_actual"] > x["eps_estimate"])
        out.append({"key": "eps_beats", "beats": beats, "n": len(s)})
    by_period = {e["period"]: e for e in c.get("estimates") or []}
    for p, key in (("0y", "consensus_fy"), ("+1y", "consensus_next_fy")):
        e = by_period.get(p)
        if e and e.get("eps_growth") is not None and e.get("eps_n"):
            out.append({"key": key, "eps_growth": e["eps_growth"], "n": e["eps_n"], "end": e.get("end_date"),
                        "rev_growth": e.get("rev_growth")})
    e = by_period.get("0y")
    if e and e.get("eps_trend_now") is not None and e.get("eps_trend_30d"):
        out.append({"key": "eps_revision_30d", "v": e["eps_trend_now"] / e["eps_trend_30d"] - 1})
    t = c.get("targets") or {}
    price = last_price if last_price is not None else t.get("current_price")
    if t.get("mean") and price and t.get("n_analysts"):
        out.append({"key": "target_upside", "v": t["mean"] / price - 1, "mean": t["mean"], "n": t["n_analysts"]})
    recos = [r for r in (c.get("recommendations") or []) if r.get("period") == "0m"]
    if recos:
        r = recos[0]
        buy, hold, sell = (r.get("strongBuy") or 0) + (r.get("buy") or 0), r.get("hold") or 0, (r.get("sell") or 0) + (r.get("strongSell") or 0)
        if buy + hold + sell:
            out.append({"key": "reco_split", "buy": buy, "hold": hold, "sell": sell})
    if annual and annual[-1].get("net_debt") is not None:
        a = annual[-1]
        if a["net_debt"] < 0:
            out.append({"key": "net_cash", "v": -a["net_debt"], "fy": a["end"]})
        elif a.get("net_debt_to_ebitda") is not None:
            out.append({"key": "leverage", "v": a["net_debt_to_ebitda"], "fy": a["end"]})
    today = (today or date.today()).isoformat()
    upcoming = [d for d in (c.get("calendar") or {}).get("earnings_dates") or [] if d >= today]
    if upcoming:
        out.append({"key": "next_earnings", "date": upcoming[0]})
    return out


# ---------------- network ---------------------------------------------------------------------
def fetch(ticker):
    """One quoteSummary call (all modules at once) + 4 statement calls."""
    import yfinance as yf
    t = yf.Ticker(ticker)
    js = t._quote._fetch(modules=MODULES)   # yfinance internal: avoids ~9 separate calls per ticker
    data = parse_summary(js)
    try:
        inc_a = t.get_income_stmt(freq="yearly")
        inc_q = t.get_income_stmt(freq="quarterly")
        bal_a = t.get_balance_sheet(freq="yearly")
        cf_a = t.get_cash_flow(freq="yearly")
        data["annual"] = enrich_annual(statement_rows(inc_a, INCOME_ROWS, 4), statement_rows(bal_a, BALANCE_ROWS, 4),
                                       statement_rows(cf_a, CASHFLOW_ROWS, 4))
        data["quarterly"] = statement_rows(inc_q, INCOME_ROWS, 6)
        for q in data["quarterly"]:
            q["net_margin"] = ratio(q.get("net_income"), q.get("revenue"))
        data["statements_error"] = None
    except Exception as e:  # noqa: BLE001
        data["annual"], data["quarterly"] = [], []
        data["statements_error"] = f"{type(e).__name__}: {e}"[:200]
    try:  # dividend history (last 10 years), per share, in the quote currency
        dv = t.dividends
        if dv is not None and len(dv):
            k = 0.01 if data["profile"].get("currency") == "GBp" else 1.0
            dv = dv[dv.index >= dv.index.max() - __import__("pandas").DateOffset(years=10)]
            data["dividends"] = [[d.strftime("%Y-%m-%d"), round(float(v) * k, 6)] for d, v in dv.items()]
        else:
            data["dividends"] = []
    except Exception as e:  # noqa: BLE001
        data["dividends"], data["dividends_error"] = [], f"{type(e).__name__}: {e}"[:200]
    return data
