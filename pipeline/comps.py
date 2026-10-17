"""Comparable companies: valuation multiples computed by us, in EUR, from
market cap = last delayed price x shares outstanding (Yahoo), and the last fiscal year's
revenue / EBITDA / net income / net debt (Yahoo financial statements).
P/E needs a positive net income, EV/EBITDA a positive EBITDA; otherwise the multiple is N/A."""
from statistics import median

from .fx import to_eur

SIZE_LARGE = 10e9   # EUR
SIZE_MID = 2e9


def size_class(mcap_eur):
    if mcap_eur is None:
        return None
    return "large" if mcap_eur >= SIZE_LARGE else ("mid" if mcap_eur >= SIZE_MID else "small")


def comp_row(company, quote, rates):
    """company: parsed company page data; quote: quotes.json entry. Returns the multiples (EUR)."""
    prof = company.get("profile") or {}
    val = company.get("valuation") or {}
    price = quote.get("last") if quote and quote.get("status") == "ok" else None
    qccy = quote.get("currency") if quote else None
    shares = val.get("shares_outstanding")
    mcap_local = price * shares if (price is not None and shares) else None
    mcap = to_eur(mcap_local, qccy, rates)
    a = (company.get("annual") or [None])[-1] or {}
    fccy = prof.get("financial_currency") or qccy
    rev, ebitda, ni, nd = (to_eur(a.get(k), fccy, rates) for k in ("revenue", "ebitda", "net_income", "net_debt"))
    ev = mcap + nd if (mcap is not None and nd is not None) else None
    return {
        "sector": prof.get("sector"), "industry": prof.get("industry"), "fy": a.get("end"),
        "price": price, "currency": qccy, "fin_currency": fccy,
        "market_cap_eur": mcap, "ev_eur": ev, "revenue_eur": rev, "ebitda_eur": ebitda, "net_income_eur": ni,
        "net_debt_eur": nd, "size": size_class(mcap),
        "pe": mcap / ni if (mcap is not None and ni and ni > 0) else None,
        "ev_ebitda": ev / ebitda if (ev is not None and ebitda and ebitda > 0) else None,
        "ev_sales": ev / rev if (ev is not None and rev and rev > 0) else None,
        "net_margin": a.get("net_margin"), "ebit_margin": a.get("ebit_margin"), "revenue_growth": a.get("revenue_growth"),
        "roe": a.get("roe"), "net_debt_to_ebitda": a.get("net_debt_to_ebitda"),
        "dividend_yield": val.get("dividend_yield"),
    }


def sector_medians(rows, keys=("pe", "ev_ebitda", "ev_sales", "net_margin", "ebit_margin", "revenue_growth", "roe")):
    by = {}
    for r in rows.values():
        if r.get("sector"):
            by.setdefault(r["sector"], []).append(r)
    out = {}
    for sec, rs in by.items():
        out[sec] = {"n": len(rs)}
        for k in keys:
            vals = [r[k] for r in rs if r.get(k) is not None]
            out[sec][k] = median(vals) if vals else None
            out[sec][k + "_n"] = len(vals)
    return out
