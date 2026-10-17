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


# ---------------- US fallback sources (FRED times out from GitHub's servers)
def test_parse_treasury_csv():
    text = ('Date,"1 Mo","2 Mo","3 Mo","4 Mo","6 Mo","1 Yr","2 Yr","3 Yr","5 Yr","7 Yr","10 Yr","20 Yr","30 Yr"\n'
            "10/16/2026,4.10,4.08,4.02,3.98,3.90,3.80,3.55,3.50,3.60,3.75,4.05,4.50,4.60\n"
            "10/15/2026,4.11,4.09,N/A,3.99,3.91,3.81,3.56,3.51,3.61,3.76,4.06,4.51,4.61\n")
    out = macro.parse_treasury_csv(text)
    assert out["DGS10"] == [("2026-10-16", 4.05), ("2026-10-15", 4.06)]
    assert out["DGS3MO"] == [("2026-10-16", 4.02)]          # N/A skipped, never filled
    assert out["DGS2"][0] == ("2026-10-16", 3.55)


def test_parse_nyfed_effr():
    obj = {"refRates": [{"effectiveDate": "2026-10-16", "type": "EFFR", "percentRate": 3.58},
                        {"effectiveDate": "2026-10-15", "type": "EFFR", "percentRate": 3.59}]}
    assert macro.parse_nyfed_effr(obj) == [("2026-10-15", 3.59), ("2026-10-16", 3.58)]
    with pytest.raises(ValueError):
        macro.parse_nyfed_effr({"refRates": []})


def test_parse_bls():
    obj = {"status": "REQUEST_SUCCEEDED", "Results": {"series": [{"seriesID": "LNS14000000", "data": [
        {"year": "2026", "period": "M09", "value": "4.3"}, {"year": "2026", "period": "M08", "value": "4.2"},
        {"year": "2025", "period": "M13", "value": "4.1"}]}]}}
    assert macro.parse_bls(obj, "LNS14000000") == [("2026-08-01", 4.2), ("2026-09-01", 4.3)]
    with pytest.raises(ValueError):
        macro.parse_bls({"status": "REQUEST_NOT_PROCESSED", "message": ["daily threshold"]}, "LNS14000000")


# ---------------- headline translation
def test_translation_only_new_english_headlines():
    from pipeline import translate
    calls = []

    def fake_tr(titles, batch_size, max_length):  # test double for the translation model
        calls.append(list(titles))
        return [{"translation_text": "FR: " + t} for t in titles]

    cache = {"old": "Ancien titre"}
    items = [{"title": "Old", "link": "old", "lang": "en"}, {"title": "Apple rises", "link": "new", "lang": "en"},
             {"title": "LVMH recule", "link": "fr1", "lang": "fr"}]
    translate.translate_new(items, cache, tr=fake_tr)
    assert calls == [["Apple rises"]]                      # cached and French headlines are not re-translated
    translate.attach(items, cache)
    assert [i["title_fr"] for i in items] == ["Ancien titre", "FR: Apple rises", None]
    assert items[1]["title"] == "Apple rises"              # original always kept


def test_translation_glossary_stock_means_share():
    from pipeline import translate
    assert translate.fix_terms("Le stock de LVMH se dirige vers la prochaine session") == "L'action LVMH se dirige vers la prochaine session"
    assert translate.fix_terms("Chute de 9,5% en un mois: le stock Vicat rebondit") == "Chute de 9,5% en un mois: l'action Vicat rebondit"
    assert translate.fix_terms("stocker des données") == "stocker des données"   # whole words only


def test_translation_time_budget_and_newest_first():
    from pipeline import translate
    seen = []

    def fake_tr(titles, batch_size, max_length):
        seen.extend(titles)
        return [{"translation_text": t.lower()} for t in titles]

    items = [{"title": f"T{i}", "link": f"l{i}", "lang": "en", "published": f"2026-10-{10 + i:02d}"} for i in range(5)]
    cache = {}
    translate.translate_new(items, cache, tr=fake_tr, budget_s=-1, batch=2)   # budget already spent
    assert cache == {}
    translate.translate_new(items, cache, tr=fake_tr, budget_s=None, batch=2)
    assert seen[:2] == ["T4", "T3"]                          # newest headlines first
    assert len(cache) == 5


def test_translate_long_text_sentence_by_sentence():
    from pipeline import translate
    calls = []

    def fake_tr(sents, batch_size, max_length):
        calls.append(list(sents))
        return [{"translation_text": "FR(" + s + ")"} for s in sents]
    out = translate.translate_text("Vicat makes cement. It was founded in 1853. The stock is listed.", tr=fake_tr)
    assert calls == [["Vicat makes cement.", "It was founded in 1853.", "The stock is listed."]]
    assert out == "FR(Vicat makes cement.) FR(It was founded in 1853.) FR(The stock is listed.)"
    assert translate.translate_text("", tr=fake_tr) is None
