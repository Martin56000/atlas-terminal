"""SEC companyfacts parsing on hand-built examples (shape copied from the real API)."""
import pytest

from pipeline import fundamentals as fa


def q(start, end, val, filed="2024-01-01", form="10-Q"):
    return {"start": start, "end": end, "val": val, "filed": filed, "form": form}


FY = [  # fiscal year Oct-Sep like Apple
    q("2022-09-25", "2022-12-31", 10, "2023-02-01"),
    q("2023-01-01", "2023-04-01", 20, "2023-05-01"),
    q("2023-04-02", "2023-07-01", 30, "2023-08-01"),
    q("2022-09-25", "2023-09-30", 100, "2023-11-01", form="10-K"),
    q("2022-09-25", "2023-04-01", 30, "2023-05-01"),   # 6-month YTD: must be ignored
]


def test_q4_derived_from_annual():
    out = fa.quarterly_with_q4(FY)
    q4 = out["2023-09-30"]
    assert q4["val"] == 40          # 100 - 10 - 20 - 30
    assert q4["derived"] is True
    assert q4["start"] == "2023-07-02"
    assert len(out) == 4            # YTD period ignored


def test_restatement_latest_filing_wins():
    entries = [q("2023-01-01", "2023-03-31", 50, "2023-05-01"), q("2023-01-01", "2023-03-31", 55, "2024-05-01")]
    assert fa.quarterly_with_q4(entries)["2023-03-31"]["val"] == 55


def test_no_q4_when_quarters_missing():
    out = fa.quarterly_with_q4([FY[0], FY[1], FY[3]])  # Q3 missing -> cannot derive, never guess
    assert "2023-09-30" not in out


def test_pick_concept_prefers_most_recent_tag():
    facts = {
        "SalesRevenueNet": {"units": {"USD": [q("2018-01-01", "2018-03-31", 1)]}},
        "RevenueFromContractWithCustomerExcludingAssessedTax": {"units": {"USD": [q("2024-01-01", "2024-03-31", 2)]}},
    }
    tag, unit, series = fa.pick_concept(facts, fa.US_GAAP["revenue"])
    assert tag == "RevenueFromContractWithCustomerExcludingAssessedTax" and unit == "USD"
    assert series["2024-03-31"]["val"] == 2


def test_build_table_margins_and_gross_from_cost():
    facts = {
        "Revenues": {"units": {"USD": [q("2024-01-01", "2024-03-31", 200)]}},
        "NetIncomeLoss": {"units": {"USD": [q("2024-01-01", "2024-03-31", 30)]}},
        "EarningsPerShareDiluted": {"units": {"USD/shares": [q("2024-01-01", "2024-03-31", 1.5)]}},
        "CostOfRevenue": {"units": {"USD": [q("2024-01-01", "2024-03-31", 150)]}},
    }
    t = fa.build_table(facts, fa.US_GAAP, 8, fa.quarterly_with_q4, "AMZN")
    row = t["rows"][0]
    assert row["gross_profit"] == 50                 # 200 - 150
    assert row["gross_margin"] == pytest.approx(0.25)
    assert row["net_margin"] == pytest.approx(0.15)
    assert row["eps_diluted"] == 1.5
    assert t["tags"]["gross_profit"] == "Revenues - CostOfRevenue"


def test_bank_has_no_gross_margin():
    facts = {"Revenues": {"units": {"USD": [q("2024-01-01", "2024-03-31", 200)]}},
             "GrossProfit": {"units": {"USD": [q("2024-01-01", "2024-03-31", 120)]}}}
    row = fa.build_table(facts, fa.US_GAAP, 8, fa.quarterly_with_q4, "JPM")["rows"][0]
    assert row["gross_margin"] is None


def test_ifrs_annual_20f():
    facts = {"Revenue": {"units": {"EUR": [q("2023-01-01", "2023-12-31", 1000, form="20-F"),
                                           q("2024-01-01", "2024-12-31", 1100, form="20-F")]}},
             "ProfitLoss": {"units": {"EUR": [q("2024-01-01", "2024-12-31", 110, form="20-F")]}}}
    t = fa.build_table(facts, fa.IFRS, 4, fa.annual_values, "SAP.DE")
    assert [r["revenue"] for r in t["rows"]] == [1000, 1100]
    assert t["rows"][-1]["net_margin"] == pytest.approx(0.10)
    assert t["unit"] == "EUR"


def test_recent_filings_links():
    subs = {"filings": {"recent": {"form": ["8-K", "4", "10-Q"], "filingDate": ["2024-05-02", "2024-05-01", "2024-05-01"],
                                   "accessionNumber": ["0000320193-24-000001", "x", "0000320193-24-000002"],
                                   "primaryDocument": ["a.htm", "b.xml", "c.htm"], "items": ["2.02", "", ""],
                                   "reportDate": ["2024-05-02", "", "2024-03-30"]}}}
    out = fa.recent_filings(subs, fa.US_FORMS, 320193)
    assert [f["form"] for f in out] == ["8-K", "10-Q"]
    assert out[0]["url"] == "https://www.sec.gov/Archives/edgar/data/320193/000032019324000001/a.htm"
