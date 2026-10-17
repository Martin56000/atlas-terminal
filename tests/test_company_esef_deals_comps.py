"""Company page, ESEF, deals and comps on small hand-built examples (shapes copied from the real APIs)."""
from datetime import date

import pandas as pd
import pytest

from pipeline import comps, company, deals, esef, fx


# ---------------- FX
def test_to_eur():
    rates = {"EUR": 1.0, "USD": 1.10, "GBP": 0.85}
    assert fx.to_eur(110, "USD", rates) == pytest.approx(100)        # 110 USD / 1.10 USD per EUR
    assert fx.to_eur(8500, "GBp", rates) == pytest.approx(100)       # 8500 pence = 85 GBP = 100 EUR
    assert fx.to_eur(5, "EUR", rates) == 5
    assert fx.to_eur(5, "JPY", rates) is None                        # unknown rate: never guessed


def test_rates_from_quotes_only_ok():
    q = {"EURUSD=X": {"status": "ok", "last": 1.1}, "EURGBP=X": {"status": "error"}}
    assert fx.rates_from_quotes(q) == {"EUR": 1.0, "USD": 1.1}


# ---------------- Yahoo quoteSummary
SUMMARY = {"quoteSummary": {"error": None, "result": [{
    "assetProfile": {"sector": "Industrials", "industry": "Building Materials", "country": "France",
                     "fullTimeEmployees": 10000, "longBusinessSummary": "Cement maker."},
    "price": {"longName": "Vicat S.A.", "currency": "EUR", "marketCap": {"raw": 2.6e9, "fmt": "2.6B"}},
    "summaryDetail": {"trailingPE": 8.5, "dividendYield": 0.035},
    "defaultKeyStatistics": {"sharesOutstanding": 44900000, "enterpriseToEbitda": 4.1},
    "financialData": {"currentPrice": 59.0, "targetMeanPrice": 70.8, "targetHighPrice": 80, "targetLowPrice": 60,
                      "numberOfAnalystOpinions": 5, "recommendationKey": "buy", "financialCurrency": "EUR"},
    "calendarEvents": {"earnings": {"earningsDate": [1793404800], "earningsAverage": 1.2}},   # 2026-10-31
    "earningsTrend": {"trend": [
        {"period": "0y", "endDate": "2026-12-31", "earningsEstimate": {"avg": 7.0, "numberOfAnalysts": 5, "growth": 0.10},
         "revenueEstimate": {"avg": 4.0e9, "numberOfAnalysts": 5, "growth": 0.04},
         "epsTrend": {"current": 7.0, "30daysAgo": 7.2}},
        {"period": "+1y", "endDate": "2027-12-31", "earningsEstimate": {"avg": 7.7, "numberOfAnalysts": 4, "growth": 0.10}, "revenueEstimate": {}, "epsTrend": {}},
        {"period": "+5y", "earningsEstimate": {}, "revenueEstimate": {}, "epsTrend": {}}]},
    "earningsHistory": {"history": [
        {"quarter": 1750982400, "epsActual": 1.5, "epsEstimate": 1.4, "surprisePercent": 0.071},   # beat
        {"quarter": 1743379200, "epsActual": 1.0, "epsEstimate": 1.1, "surprisePercent": -0.09}]},  # miss
    "recommendationTrend": {"trend": [{"period": "0m", "strongBuy": 1, "buy": 2, "hold": 2, "sell": 0, "strongSell": 0}]},
}]}}


def test_parse_summary():
    d = company.parse_summary(SUMMARY)
    assert d["profile"]["sector"] == "Industrials" and d["profile"]["name"] == "Vicat S.A."
    assert d["valuation"]["market_cap_yahoo"] == 2.6e9                   # {'raw': ...} unwrapped
    assert d["calendar"]["earnings_dates"] == ["2026-10-31"]
    assert [e["period"] for e in d["estimates"]] == ["0y", "+1y"]          # empty +5y dropped
    assert d["surprises"][0]["quarter"] < d["surprises"][1]["quarter"]       # oldest first
    with pytest.raises(ValueError):
        company.parse_summary({"quoteSummary": {"result": [], "error": {"code": "Not Found"}}})


def test_statements_and_derived_ratios():
    cols = [pd.Timestamp("2024-12-31"), pd.Timestamp("2025-12-31")]
    inc = pd.DataFrame({cols[0]: [1000.0, 200.0, 100.0, 50.0], cols[1]: [1100.0, 230.0, 120.0, 66.0]},
                       index=["TotalRevenue", "EBITDA", "OperatingIncome", "NetIncomeCommonStockholders"])
    bal = pd.DataFrame({cols[1]: [500.0, 140.0, 600.0]}, index=["TotalDebt", "CashAndCashEquivalents", "StockholdersEquity"])
    cf = pd.DataFrame({cols[1]: [180.0, -80.0]}, index=["OperatingCashFlow", "CapitalExpenditure"])
    rows = company.enrich_annual(company.statement_rows(inc, company.INCOME_ROWS, 4),
                                 company.statement_rows(bal, company.BALANCE_ROWS, 4),
                                 company.statement_rows(cf, company.CASHFLOW_ROWS, 4))
    last = rows[-1]
    assert last["revenue_growth"] == pytest.approx(0.10)     # 1100 / 1000 - 1
    assert last["net_margin"] == pytest.approx(0.06)         # 66 / 1100
    assert last["net_debt"] == 360                           # 500 - 140
    assert last["net_debt_to_ebitda"] == pytest.approx(360 / 230)
    assert last["fcf"] == 100                                # 180 + (-80)
    assert last["roe"] == pytest.approx(0.11)                # 66 / 600
    assert rows[0]["revenue_growth"] is None


def test_facts_are_only_built_from_available_data():
    c = company.parse_summary(SUMMARY)
    c["annual"] = [{"end": "2024-12-31", "revenue": 1000, "net_margin": 0.05},
                   {"end": "2025-12-31", "revenue": 1100, "net_margin": 0.06, "revenue_growth": 0.10, "net_debt": 360, "net_debt_to_ebitda": 1.5}]
    c["quarterly"] = [{"end": "2025-06-30", "revenue": 500}, {"end": "2026-06-30", "revenue": 550}]
    f = {x["key"]: x for x in company.facts(c, last_price=59.0, today=date(2026, 10, 17))}
    assert f["rev_growth_fy"]["v"] == pytest.approx(0.10)
    assert f["net_margin_fy"]["delta_pts"] == pytest.approx(1.0)        # 6 % vs 5 % = +1 pt
    assert f["rev_growth_q"]["v"] == pytest.approx(0.10)                # 550 vs 500, one year apart
    assert (f["eps_beats"]["beats"], f["eps_beats"]["n"]) == (1, 2)
    assert f["consensus_fy"]["eps_growth"] == 0.10 and f["consensus_fy"]["n"] == 5
    assert f["eps_revision_30d"]["v"] == pytest.approx(7.0 / 7.2 - 1)
    assert f["target_upside"]["v"] == pytest.approx(70.8 / 59.0 - 1)    # +20 %
    assert (f["reco_split"]["buy"], f["reco_split"]["hold"], f["reco_split"]["sell"]) == (3, 2, 0)
    assert f["leverage"]["v"] == 1.5
    assert f["next_earnings"]["date"] == "2026-10-31"
    assert company.facts({}) == []                                       # nothing invented


# ---------------- ESEF
OIM = {"documentInfo": {}, "facts": {
    "a": {"value": "3854437000.0", "dimensions": {"concept": "ifrs-full:RevenueFromContractsWithCustomers", "entity": "scheme:X",
                                                   "period": "2025-01-01T00:00:00/2026-01-01T00:00:00", "unit": "iso4217:EUR"}},
    "b": {"value": "3500000000.0", "dimensions": {"concept": "ifrs-full:RevenueFromContractsWithCustomers", "entity": "scheme:X",
                                                   "period": "2024-01-01T00:00:00/2025-01-01T00:00:00", "unit": "iso4217:EUR"}},
    "c": {"value": "306658000.0", "dimensions": {"concept": "ifrs-full:ProfitLoss", "entity": "scheme:X",
                                                  "period": "2025-01-01T00:00:00/2026-01-01T00:00:00", "unit": "iso4217:EUR"}},
    "seg": {"value": "999.0", "dimensions": {"concept": "ifrs-full:RevenueFromContractsWithCustomers", "entity": "scheme:X",
                                              "period": "2025-01-01T00:00:00/2026-01-01T00:00:00", "unit": "iso4217:EUR",
                                              "ifrs-full:SegmentsAxis": "x:France"}},
    "half": {"value": "1.0", "dimensions": {"concept": "ifrs-full:ProfitLoss", "entity": "scheme:X",
                                             "period": "2025-01-01T00:00:00/2025-07-01T00:00:00", "unit": "iso4217:EUR"}},
    "cash": {"value": "500000000", "dimensions": {"concept": "ifrs-full:CashAndCashEquivalents", "entity": "scheme:X",
                                                   "period": "2026-01-01T00:00:00", "unit": "iso4217:EUR"}},
}}


def test_esef_extract_group_totals_only():
    years, ccy = esef.extract(OIM)
    assert ccy == "EUR"
    assert years["2025-12-31"]["revenue"] == 3854437000.0      # segment fact (999) ignored
    assert years["2025-12-31"]["net_income"] == 306658000.0   # half-year fact ignored
    assert years["2025-12-31"]["cash"] == 500000000.0         # instant at year end
    rows = esef.table(years)
    assert rows[-1]["revenue_growth"] == pytest.approx(3854437000 / 3500000000 - 1)
    assert rows[-1]["net_margin"] == pytest.approx(306658000 / 3854437000)


def test_esef_period_parsing():
    assert esef.parse_period("2025-01-01T00:00:00/2026-01-01T00:00:00") == ("2025-01-01", "2025-12-31")
    assert esef.parse_period("2026-01-01T00:00:00") == (None, "2025-12-31")


def test_esef_entity_choice():
    fr = [{"country": "FR"}]
    be = [{"country": "BE"}]
    chosen, err = esef.pick_entity([("L1", "ORANGE", fr), ("L2", "ORANGE BELGIUM", be)], "FR", "Orange")
    assert chosen[0] == "L1" and err is None
    chosen, err = esef.pick_entity([("L1", "SEB SA", fr), ("L3", "SEB INTERNATIONALE", fr)], "FR", "SEB")
    assert chosen[0] == "L1"                                   # exact normalised name wins
    chosen, err = esef.pick_entity([("L1", "ALPHA ONE", fr), ("L3", "ALPHA TWO", fr)], "FR", "Alpha")
    assert chosen is None and err.startswith("ambiguous")      # never guessed
    chosen, err = esef.pick_entity([("L2", "ORANGE BELGIUM", be)], "FR", "Orange")
    assert chosen is None


# ---------------- deals
def test_ma_headline_detection():
    assert deals.ma_match("Vinci to acquire airport operator for $2bn")
    assert deals.ma_match("LVMH annonce le rachat de la maison X")
    assert deals.ma_match("Lancement d'une OPA sur Exail")
    assert deals.ma_match("SAP buyback update shows what it means") is None          # buyback is not M&A
    assert deals.ma_match("Programme de rachat d'actions de TotalEnergies") is None
    assert deals.ma_match("Apple beats estimates") is None


def test_deal_filings():
    subs = {"filings": {"recent": {
        "form": ["8-K", "8-K", "SC 13D", "10-Q", "SCHEDULE 13D/A"], "filingDate": ["2026-10-01", "2026-09-01", "2026-08-01", "2026-07-01", "2026-06-01"],
        "accessionNumber": ["a-1", "b-2", "c-3", "d-4", "e-5"], "primaryDocument": ["a.htm", "b.htm", "c.htm", "d.htm", "e.htm"],
        "items": ["2.02,9.01", "1.01,9.01", "", "", ""]}}}
    out = deals.deal_filings(subs, 123)
    assert [(f["form"], f["kinds"]) for f in out] == [("8-K", ["material_agreement"]), ("SC 13D", ["stake_13d"]), ("SCHEDULE 13D/A", ["stake_13d"])]


# ---------------- comps
def test_comp_row_hand_example():
    rates = {"EUR": 1.0, "USD": 1.25}
    c = {"profile": {"sector": "Tech", "financial_currency": "USD"}, "valuation": {"shares_outstanding": 1_000_000},
         "annual": [{"end": "2025-12-31", "revenue": 50e6, "ebitda": 12.5e6, "net_income": 5e6, "net_debt": 25e6}]}
    q = {"status": "ok", "last": 100.0, "currency": "EUR"}
    r = comps.comp_row(c, q, rates)
    assert r["market_cap_eur"] == 100e6                        # 100 EUR x 1m shares
    assert r["net_debt_eur"] == 20e6                           # 25m USD / 1.25
    assert r["ev_eur"] == 120e6
    assert r["pe"] == pytest.approx(100e6 / 4e6)               # NI 5m USD = 4m EUR -> P/E 25
    assert r["ev_ebitda"] == pytest.approx(120e6 / 10e6)       # 12
    assert r["ev_sales"] == pytest.approx(120e6 / 40e6)        # 3
    assert r["size"] == "small"


def test_comp_multiples_na_when_not_meaningful():
    c = {"profile": {"sector": "Tech", "financial_currency": "EUR"}, "valuation": {"shares_outstanding": 10},
         "annual": [{"end": "2025-12-31", "revenue": 100.0, "ebitda": -5.0, "net_income": -1.0, "net_debt": None}]}
    r = comps.comp_row(c, {"status": "ok", "last": 10.0, "currency": "EUR"}, {"EUR": 1.0})
    assert r["pe"] is None and r["ev_ebitda"] is None and r["ev_eur"] is None


def test_sector_medians_and_size():
    rows = {"A": {"sector": "S", "pe": 10}, "B": {"sector": "S", "pe": 20}, "C": {"sector": "S", "pe": None}, "D": {"sector": "T", "pe": 5}}
    m = comps.sector_medians(rows)
    assert m["S"]["pe"] == 15 and m["S"]["pe_n"] == 2 and m["S"]["n"] == 3
    assert (comps.size_class(15e9), comps.size_class(5e9), comps.size_class(1e9), comps.size_class(None)) == ("large", "mid", "small", None)
