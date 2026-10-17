"""Fundamentals from SEC EDGAR (companyfacts + submissions). No API key, but a
descriptive User-Agent with a contact email and <= SEC_MAX_RPS requests/second."""
import time
from datetime import date, timedelta

import requests

from . import config

US_GAAP = {
    "revenue": ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet",
                "RevenueFromContractWithCustomerIncludingAssessedTax", "RevenuesNetOfInterestExpense"],
    "net_income": ["NetIncomeLoss"],
    "eps_diluted": ["EarningsPerShareDiluted"],
    "gross_profit": ["GrossProfit"],
    "cost_of_revenue": ["CostOfRevenue", "CostOfGoodsAndServicesSold"],
}
IFRS = {
    "revenue": ["Revenue", "RevenueFromContractsWithCustomers", "RevenueFromSaleOfGoods"],
    "net_income": ["ProfitLossAttributableToOwnersOfParent", "ProfitLoss"],
    "eps_diluted": ["DilutedEarningsLossPerShare", "BasicAndDilutedEarningsLossPerShare"],
    "gross_profit": ["GrossProfit"],
    "cost_of_revenue": ["CostOfSales"],
}
NO_GROSS_MARGIN = {"JPM", "HSBA.L"}  # banks: gross margin is not meaningful
US_FORMS = ("10-K", "10-Q", "8-K", "10-K/A", "10-Q/A", "8-K/A")
FOREIGN_FORMS = ("20-F", "6-K", "20-F/A", "6-K/A")


# ---------- pure parsing helpers (unit-tested) --------------------------------
def _d(s):
    return date.fromisoformat(s)


def duration_days(e):
    return (_d(e["end"]) - _d(e["start"])).days


def dedupe_periods(entries):
    """One value per (start, end): the most recently filed one (restatements win)."""
    best = {}
    for e in entries:
        if "start" not in e or "end" not in e:
            continue
        k = (e["start"], e["end"])
        if k not in best or e.get("filed", "") > best[k].get("filed", ""):
            best[k] = e
    return list(best.values())


def quarterly_with_q4(entries):
    """Quarterly values; Q4 derived as fiscal year - Q1 - Q2 - Q3 when not filed alone.
    Returns {end_date: {"start", "end", "val", "derived": bool}}."""
    periods = dedupe_periods(entries)
    quarters = {p["end"]: {"start": p["start"], "end": p["end"], "val": p["val"], "derived": False}
                for p in periods if 80 <= duration_days(p) <= 100}
    annuals = [p for p in periods if 350 <= duration_days(p) <= 380]
    for a in annuals:
        if a["end"] in quarters:
            continue
        a_start, a_end = _d(a["start"]), _d(a["end"])
        inside = sorted((q for q in quarters.values()
                         if not q["derived"] and _d(q["start"]) >= a_start - timedelta(days=7)
                         and _d(q["end"]) < a_end), key=lambda q: q["end"])
        if len(inside) != 3:
            continue
        # the 3 quarters must chain from the fiscal-year start without gaps
        if abs((_d(inside[0]["start"]) - a_start).days) > 7:
            continue
        if any((_d(inside[i + 1]["start"]) - _d(inside[i]["end"])).days > 7 for i in range(2)):
            continue
        q4_start = (_d(inside[2]["end"]) + timedelta(days=1)).isoformat()
        quarters[a["end"]] = {"start": q4_start, "end": a["end"],
                              "val": a["val"] - sum(q["val"] for q in inside), "derived": True}
    return quarters


def annual_values(entries, forms=("20-F", "20-F/A", "10-K", "10-K/A")):
    periods = dedupe_periods([e for e in entries if e.get("form") in forms] or entries)
    return {p["end"]: {"start": p["start"], "end": p["end"], "val": p["val"], "derived": False}
            for p in periods if 350 <= duration_days(p) <= 380}


def pick_unit(units, per_share=False):
    keys = [k for k in units if ("/shares" in k) == per_share]
    if not keys:
        return None, None
    key = "USD" if "USD" in keys else ("USD/shares" if "USD/shares" in keys else keys[0])
    return key, units[key]


def pick_concept(taxonomy_facts, candidates, per_share=False, period_fn=quarterly_with_q4):
    """First concept with the most recent period wins (companies switch tags over time)."""
    best = None
    for name in candidates:
        fact = taxonomy_facts.get(name)
        if not fact:
            continue
        unit, entries = pick_unit(fact.get("units", {}), per_share)
        if not entries:
            continue
        series = period_fn(entries)
        if not series:
            continue
        latest = max(series)
        if best is None or latest > best[3]:
            best = (name, unit, series, latest)
    return (best[0], best[1], best[2]) if best else (None, None, {})


def build_table(taxonomy_facts, concepts, n, period_fn, ticker):
    rev_tag, unit, rev = pick_concept(taxonomy_facts, concepts["revenue"], period_fn=period_fn)
    ni_tag, ni_unit, ni = pick_concept(taxonomy_facts, concepts["net_income"], period_fn=period_fn)
    eps_tag, eps_unit, eps = pick_concept(taxonomy_facts, concepts["eps_diluted"], per_share=True, period_fn=period_fn)
    gp_tag, _, gp = pick_concept(taxonomy_facts, concepts["gross_profit"], period_fn=period_fn)
    cost_tag, _, cost = pick_concept(taxonomy_facts, concepts["cost_of_revenue"], period_fn=period_fn)

    ends = sorted(rev or ni, reverse=True)[:n]
    rows = []
    gross_src = gp_tag
    for end in sorted(ends):
        r = rev.get(end)
        i = ni.get(end)
        e = eps.get(end)
        g = gp.get(end)
        gross_src = gp_tag if g else gross_src
        if g is None and r is not None and cost.get(end) is not None:
            g = {"val": r["val"] - cost[end]["val"], "derived": r["derived"] or cost[end]["derived"]}
            gross_src = f"{rev_tag} - {cost_tag}"
        if ticker in NO_GROSS_MARGIN:
            g, gross_src = None, None
        rv = r["val"] if r else None
        rows.append({
            "start": (r or i or {}).get("start"), "end": end,
            "revenue": rv,
            "net_income": i["val"] if i else None,
            "eps_diluted": e["val"] if e else None,
            "gross_profit": g["val"] if g else None,
            "gross_margin": (g["val"] / rv) if (g and rv) else None,
            "net_margin": (i["val"] / rv) if (i and rv) else None,
            "derived": sorted({k for k, s in (("revenue", r), ("net_income", i), ("eps_diluted", e), ("gross_profit", g))
                               if s and s.get("derived")}),
        })
    return {"rows": rows, "unit": unit, "eps_unit": eps_unit,
            "tags": {"revenue": rev_tag, "net_income": ni_tag, "eps_diluted": eps_tag, "gross_profit": gross_src}}


def latest_end(table):
    return table["rows"][-1]["end"] if table["rows"] else ""


def choose_foreign_table(facts, ticker):
    ifrs = build_table(facts.get("ifrs-full", {}), IFRS, 4, annual_values, ticker)
    gaap = build_table(facts.get("us-gaap", {}), US_GAAP, 4, annual_values, ticker)
    if latest_end(gaap) > latest_end(ifrs):
        return "annual_usgaap_20f", gaap
    return "annual_ifrs_20f", ifrs


def is_recent(table, today=None, max_age_days=800):
    """Last period must end within ~2 years, otherwise the data is too old to show as current."""
    end = latest_end(table)
    if not end:
        return False
    today = today or date.today()
    return (today - _d(end)).days <= max_age_days


def recent_filings(submissions, forms, cik, n=15):
    rec = submissions.get("filings", {}).get("recent", {})
    out = []
    for i, form in enumerate(rec.get("form", [])):
        if form not in forms:
            continue
        acc = rec["accessionNumber"][i]
        doc = rec["primaryDocument"][i]
        out.append({
            "form": form, "filed": rec["filingDate"][i], "report_date": (rec.get("reportDate") or [None] * (i + 1))[i],
            "items": (rec.get("items") or [""] * (i + 1))[i],
            "url": f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc.replace('-', '')}/{doc}",
        })
        if len(out) >= n:
            break
    return out


# ---------- network ------------------------------------------------------------
class SecClient:
    def __init__(self):
        self.s = requests.Session()
        self.s.headers.update({"User-Agent": config.sec_user_agent(), "Accept-Encoding": "gzip, deflate"})
        self._last = 0.0

    def get_json(self, url):
        wait = 1.0 / config.SEC_MAX_RPS - (time.time() - self._last)
        if wait > 0:
            time.sleep(wait)
        self._last = time.time()
        r = self.s.get(url, timeout=60)
        r.raise_for_status()
        return r.json()


def cik_map(client):
    raw = client.get_json(config.SEC_TICKERS_URL)
    return {v["ticker"].upper(): int(v["cik_str"]) for v in raw.values()}


def fetch_company(client, ticker, ciks):
    info = config.BY_TICKER[ticker]
    if info["kind"] == "etf":
        return {"kind": "na", "reason": "etf"}
    sec_ticker = ticker if info["region"] == "US" else info.get("adr")
    if not sec_ticker:
        return {"kind": "na", "reason": "no_free_source"}
    cik = ciks.get(sec_ticker.upper())
    if not cik:
        raise RuntimeError(f"CIK not found for {sec_ticker} in SEC company_tickers.json")
    facts = client.get_json(config.SEC_FACTS_URL.format(cik=cik)).get("facts", {})
    subs = client.get_json(config.SEC_SUBMISSIONS_URL.format(cik=cik))
    if info["region"] == "US":
        table = build_table(facts.get("us-gaap", {}), US_GAAP, 8, quarterly_with_q4, ticker)
        kind, forms = "quarterly_us_gaap", US_FORMS
    else:
        # 20-F filers report in IFRS (most) or US GAAP (e.g. ASML): keep the most recent one
        kind, table = choose_foreign_table(facts, ticker)
        forms = FOREIGN_FORMS
    if not is_recent(table):
        last = table["rows"][-1]["end"] if table["rows"] else None
        return {"kind": "na", "reason": "no_recent_sec_data", "last_period": last, "cik": cik, "sec_ticker": sec_ticker,
                "filings": recent_filings(subs, forms, cik)}
    return {"kind": kind, "cik": cik, "sec_ticker": sec_ticker, "entity": subs.get("name"),
            "fiscal_year_end": subs.get("fiscalYearEnd"), **table,
            "filings": recent_filings(subs, forms, cik)}
