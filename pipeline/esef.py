"""European annual reports in ESEF format, from filings.xbrl.org (free, no key).

1. find the company's legal entity (LEI) by name, restricted to its country
2. take its most recent annual report (xBRL-JSON, which also contains the prior-year comparatives)
3. read a few IFRS concepts reported WITHOUT extra dimensions (group totals, not segments)

The API may change or rate-limit; any failure is reported per company, never filled in."""
import re
from datetime import date, timedelta

import requests

BASE = "https://filings.xbrl.org"
HEADERS = {"User-Agent": "Atlas Terminal (student project)", "Accept": "application/vnd.api+json, application/json"}

CONCEPTS = {
    "revenue": ["ifrs-full:Revenue", "ifrs-full:RevenueFromContractsWithCustomers", "ifrs-full:RevenueFromSaleOfGoods"],
    "ebit": ["ifrs-full:ProfitLossFromOperatingActivities"],
    "net_income": ["ifrs-full:ProfitLossAttributableToOwnersOfParent", "ifrs-full:ProfitLoss"],
    "eps_diluted": ["ifrs-full:DilutedEarningsLossPerShare", "ifrs-full:BasicAndDilutedEarningsLossPerShare"],
    "op_cash_flow": ["ifrs-full:CashFlowsFromUsedInOperatingActivities"],
    "capex": ["ifrs-full:PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities"],
    "dividends_paid": ["ifrs-full:DividendsPaidClassifiedAsFinancingActivities"],
}
INSTANT = {
    "cash": ["ifrs-full:CashAndCashEquivalents"],
    "equity": ["ifrs-full:EquityAttributableToOwnersOfParent", "ifrs-full:Equity"],
    "total_assets": ["ifrs-full:Assets"],
}
BASE_DIMS = {"concept", "entity", "period", "unit", "language"}


def norm_name(s):
    import unicodedata
    s = unicodedata.normalize("NFD", s or "").encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z0-9]+", " ", s)                      # "A/S" -> "a s", "N.V." -> "n v"
    s = re.sub(r"\b(sa|se|s a|nv|n v|ag|spa|s p a|plc|ab|asa|oyj|a s|as|group|groupe|holding|holdings|company|co)\b", " ", s)
    return re.sub(r"[^a-z0-9]+", "", s)


def parse_period(p):
    """'2025-01-01T00:00:00/2026-01-01T00:00:00' -> ('2025-01-01', '2025-12-31'); instant -> (None, day before)."""
    def day(x):
        return date.fromisoformat(x[:10])
    if "/" in p:
        a, b = p.split("/")
        end = day(b) - timedelta(days=1) if "T00:00:00" in b else day(b)
        return day(a).isoformat(), end.isoformat()
    end = day(p) - timedelta(days=1) if "T00:00:00" in p else day(p)
    return None, end.isoformat()


def extract(oim):
    """xBRL-JSON (OIM) -> {fiscal_year_end: {field: value}}, plus the currency."""
    durations, instants, currency = {}, {}, None
    for f in (oim.get("facts") or {}).values():
        dims = f.get("dimensions") or {}
        if set(dims) - BASE_DIMS:          # segment / axis breakdowns are skipped
            continue
        concept, period = dims.get("concept"), dims.get("period")
        if not concept or not period:
            continue
        try:
            val = float(f.get("value"))
        except (TypeError, ValueError):
            continue
        start, end = parse_period(period)
        unit = dims.get("unit") or ""
        if start:
            days = (date.fromisoformat(end) - date.fromisoformat(start)).days
            if not 350 <= days <= 380:
                continue
            durations.setdefault(end, {}).setdefault(concept, val)
            if unit.startswith("iso4217:") and "/" not in unit and currency is None:
                currency = unit.split(":")[1]
        else:
            instants.setdefault(end, {}).setdefault(concept, val)
    years = {}
    for end, cvals in durations.items():
        row = {}
        for field, names in CONCEPTS.items():
            row[field] = next((cvals[n] for n in names if n in cvals), None)
        iv = instants.get(end, {})
        for field, names in INSTANT.items():
            row[field] = next((iv[n] for n in names if n in iv), None)
        if any(v is not None for v in row.values()):
            years[end] = row
    return years, currency


def table(years):
    rows = []
    for end in sorted(years)[-4:]:
        r = {"end": end, **years[end]}
        rv = r.get("revenue")
        r["ebit_margin"] = r["ebit"] / rv if (r.get("ebit") is not None and rv) else None
        r["net_margin"] = r["net_income"] / rv if (r.get("net_income") is not None and rv) else None
        r["fcf"] = (r["op_cash_flow"] - abs(r["capex"])) if (r.get("op_cash_flow") is not None and r.get("capex") is not None) else None
        rows.append(r)
    for prev, cur in zip(rows, rows[1:]):
        cur["revenue_growth"] = (cur["revenue"] / prev["revenue"] - 1) if (cur.get("revenue") and prev.get("revenue")) else None
    if rows:
        rows[0]["revenue_growth"] = None
    return rows


def pick_entity(candidates, country, wanted_name):
    """candidates: [(lei, name, [filings])]. Prefer filers in the company's country; a company registered
    abroad (e.g. Airbus SE, Dutch) is accepted only on an exact normalised name match. Several plausible
    matches are reported as ambiguous, never guessed."""
    wanted = norm_name(wanted_name)
    in_country = [c for c in candidates if any((f.get("country") or "").upper() == country for f in c[2])]
    exact_any = [c for c in candidates if norm_name(c[1]) == wanted and c[2]]
    if in_country:
        exact = [c for c in in_country if norm_name(c[1]) == wanted]
        pool = exact or in_country
    elif exact_any:
        pool = exact_any
    else:
        return None, "no ESEF filer with this name in " + country
    if len(pool) > 1:
        return None, "ambiguous: " + "; ".join(c[1] for c in pool[:4])
    return pool[0], None


# ---------------- network ---------------------------------------------------------------------
def _get(session, path, params=None):
    r = session.get(BASE + path, params=params, headers=HEADERS, timeout=60)
    r.raise_for_status()
    return r.json()


def entity_filings(session, lei):
    js = _get(session, f"/api/entities/{lei}/filings", {"page[size]": 50})
    return [f.get("attributes", {}) for f in js.get("data") or []]


def find_entity(session, search, country, wanted_name, known_lei=None):
    if known_lei:
        return known_lei, None, entity_filings(session, known_lei)
    flt = '[{"name":"name","op":"ilike","val":"%' + search.replace('"', "") + '%"}]'
    js = _get(session, "/api/entities", {"filter": flt, "page[size]": 10})
    cands = []
    for e in (js.get("data") or [])[:6]:
        a = e.get("attributes") or {}
        lei = a.get("identifier")
        if lei:
            cands.append((lei, a.get("name") or "", entity_filings(session, lei)))
    chosen, err = pick_entity(cands, country, wanted_name)
    if not chosen:
        raise LookupError(err or "not found")
    return chosen[0], chosen[1], chosen[2]


def fold(s):
    """'Société Générale' -> 'Societe Generale' (entity names in the register are mostly unaccented)."""
    import unicodedata
    return unicodedata.normalize("NFD", s or "").encode("ascii", "ignore").decode()


ESEF_COUNTRIES = {"FR", "DE", "NL", "BE", "IT", "ES", "PT", "DK", "SE", "FI", "NO", "GB", "AT", "IE", "PL", "GR", "CZ"}  # CH is outside ESEF


def fetch(info, known_lei=None, search=None):
    if info["country"] not in ESEF_COUNTRIES:
        raise LookupError(f"{info['country']}: no ESEF obligation (not in the EU/EEA)")
    s = requests.Session()
    lei, ent_name, filings = find_entity(s, search or fold(info["name"]), info["country"], info["name"], known_lei)
    annual = [f for f in filings if f.get("json_url") and f.get("period_end")]
    if not annual:
        raise LookupError("no ESEF report with machine-readable data")
    # latest period first; for the same period keep the most recently processed version
    annual.sort(key=lambda f: (f["period_end"], f.get("processed") or ""), reverse=True)
    latest = annual[0]
    oim = _get(s, latest["json_url"])
    years, currency = extract(oim)
    if not years:
        raise ValueError("report found but no group-level IFRS figures could be read")
    return {"lei": lei, "entity": ent_name, "currency": currency, "period_end": latest["period_end"],
            "report_url": BASE + latest["report_url"] if latest.get("report_url") else None,
            "viewer_url": BASE + latest["viewer_url"] if latest.get("viewer_url") else None,
            "rows": table(years), "n_reports": len(annual)}
