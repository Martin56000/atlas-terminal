"""Regression tests for problems seen on the first live run (17 Oct 2026)."""
from datetime import date

import pytest

from pipeline import fundamentals as fa
from pipeline import macro, news


def q(start, end, val, form="20-F", filed="2026-03-01"):
    return {"start": start, "end": end, "val": val, "form": form, "filed": filed}


def test_build_table_without_any_row_does_not_crash():
    # ASML case: nothing under ifrs-full -> empty table, no exception
    t = fa.build_table({}, fa.IFRS, 4, fa.annual_values, "ASML.AS")
    assert t["rows"] == []


def test_foreign_filer_reporting_in_us_gaap_is_picked():
    facts = {
        "ifrs-full": {"Revenue": {"units": {"EUR": [q("2016-01-01", "2016-12-31", 1)]}}},
        "us-gaap": {"Revenues": {"units": {"EUR": [q("2025-01-01", "2025-12-31", 2)]}}},
    }
    kind, table = fa.choose_foreign_table(facts, "ASML.AS")
    assert kind == "annual_usgaap_20f"
    assert table["rows"][-1]["revenue"] == 2


def test_old_data_is_not_shown_as_current():
    old = {"rows": [{"end": "2017-12-31"}]}
    recent = {"rows": [{"end": "2025-12-31"}]}
    assert fa.is_recent(old, today=date(2026, 10, 17)) is False
    assert fa.is_recent(recent, today=date(2026, 10, 17)) is True
    assert fa.is_recent({"rows": []}, today=date(2026, 10, 17)) is False


def test_ecb_most_recent_series_wins():
    old = ("ICP/M.U2.N.000000.4.ANR", [("2025-10", 2.1), ("2025-11", 2.2)])
    new = ("HICP/M.U2.N.000000.4D0.ANR", [("2025-11", 2.2), ("2026-09", 2.0)])
    assert macro.most_recent([old, new])[0] == "HICP/M.U2.N.000000.4D0.ANR"
    with pytest.raises(ValueError):
        macro.most_recent([("x", [])])


def test_rss_fetch_rejects_html_page(monkeypatch):
    import requests

    class Resp:
        status_code = 200
        headers = {"content-type": "text/html"}
        content = b"<!DOCTYPE html><html><body>consent</body></html>"

        def raise_for_status(self):
            pass
    monkeypatch.setattr(requests, "get", lambda *a, **k: Resp())
    with pytest.raises(ValueError, match="not an RSS feed"):
        news.fetch_rss("https://news.google.com/rss/search?q=x")


def test_rss_fetch_parses_rss(monkeypatch):
    import requests

    class Resp:
        status_code = 200
        headers = {"content-type": "application/rss+xml"}
        content = (b'<?xml version="1.0"?><rss version="2.0"><channel><item><title>Apple rises - Reuters</title>'
                   b'<link>https://x/1</link><pubDate>Fri, 16 Oct 2026 20:00:00 GMT</pubDate>'
                   b'<source url="https://reuters.com">Reuters</source></item></channel></rss>')

        def raise_for_status(self):
            pass
    monkeypatch.setattr(requests, "get", lambda *a, **k: Resp())
    items = news.parse_google_feed(news.fetch_rss("u"), "Google News EN", "en")
    assert items[0]["title"] == "Apple rises" and items[0]["publisher"] == "Reuters"
    assert items[0]["published"] == "2026-10-16T20:00:00+00:00"
