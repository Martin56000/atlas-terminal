from datetime import datetime, timezone

import pandas as pd
import pytest

from pipeline import macro, market, news, sentiment, store


# ---------------- market
def test_gbp_pence_conversion():
    f = pd.DataFrame({"Close": [1234.5], "Adj Close": [1200.0], "Volume": [10]},
                     index=pd.to_datetime(["2024-01-02"]))
    out, cur = market.apply_currency(f, "GBp")
    assert cur == "GBP"
    assert out["Close"].iloc[0] == pytest.approx(12.345)
    assert out["Adj Close"].iloc[0] == pytest.approx(12.0)
    assert out["Volume"].iloc[0] == 10                  # volume is not a price


def test_completed_bars_drops_todays_unfinished_bar():
    idx = pd.to_datetime(["2026-10-15", "2026-10-16"])
    f = pd.DataFrame({"Close": [1.0, 2.0]}, index=idx)
    during = datetime(2026, 10, 16, 15, 0, tzinfo=timezone.utc)   # 11:00 New York, session open
    after = datetime(2026, 10, 16, 21, 0, tzinfo=timezone.utc)    # 17:00 New York, closed
    assert len(market.completed_bars(f, "XNYS", during)) == 1
    assert len(market.completed_bars(f, "XNYS", after)) == 2


def test_safe_name():
    assert market.safe_name("^GDAXI") == "_GDAXI"
    assert market.safe_name("EURUSD=X") == "EURUSD_X"
    assert market.safe_name("NOVO-B.CO") == "NOVO-B.CO"


# ---------------- macro
def test_parse_fred_csv_skips_missing():
    text = "observation_date,DGS10\n2024-01-01,.\n2024-01-02,3.95\n2024-01-03,3.91\n"
    assert macro.parse_fred_csv(text, "DGS10") == [("2024-01-02", 3.95), ("2024-01-03", 3.91)]


def test_parse_fred_csv_rejects_garbage():
    with pytest.raises(ValueError):
        macro.parse_fred_csv("<html>error</html>", "DGS10")


def test_cpi_yoy_hand_example():
    pts = [(f"2023-{m:02d}-01", 100.0 + m) for m in range(1, 13)] + [("2024-01-01", 107.1)]
    # Jan-2024 vs Jan-2023: 107.1 / 101 - 1 = 6.0396 %
    out = macro.yoy(pts)
    assert out == [("2024-01-01", pytest.approx(6.039604, abs=1e-6))]


def test_parse_ecb_csv():
    text = "KEY,FREQ,TIME_PERIOD,OBS_VALUE\nICP.M,M,2024-08,2.2\nICP.M,M,2024-09,1.7\n"
    assert macro.parse_ecb_csv(text) == [("2024-08", 2.2), ("2024-09", 1.7)]


# ---------------- news
def test_strip_publisher():
    assert news.strip_publisher("Apple beats estimates - Reuters", "Reuters") == "Apple beats estimates"
    assert news.strip_publisher("No suffix here", "Reuters") == "No suffix here"


def test_merge_latest_dedupes_and_sorts():
    items = [
        {"title": "A", "link": "l1", "published": "2024-01-01T10:00:00+00:00"},
        {"title": "B", "link": "l2", "published": "2024-01-03T10:00:00+00:00"},
        {"title": "a", "link": "l3", "published": "2024-01-02T10:00:00+00:00"},  # same title as A
        {"title": "C", "link": "l2", "published": "2024-01-04T10:00:00+00:00"},  # same link as B
    ]
    out = news.merge_latest(items, 10)
    assert [i["title"] for i in out] == ["C", "a"]


def test_parse_yahoo_news_both_formats():
    raw = [
        {"title": "Old", "publisher": "Bloomberg", "link": "u1", "providerPublishTime": 1700000000},
        {"content": {"title": "New", "provider": {"displayName": "Motley Fool"},
                     "canonicalUrl": {"url": "u2"}, "pubDate": "2024-05-01T12:00:00Z"}},
    ]
    out = news.parse_yahoo_news(raw)
    assert [(i["title"], i["publisher"], i["feed"]) for i in out] == [("Old", "Bloomberg", "Yahoo"), ("New", "Motley Fool", "Yahoo")]
    assert out[1]["published"] == "2024-05-01T12:00:00+00:00"


def test_sentiment_scores_only_new_english_headlines():
    calls = []

    def fake_clf(titles, batch_size):  # test double for FinBERT
        calls.append(list(titles))
        return [{"label": "Positive", "score": 0.9} for _ in titles]

    cache = {"old": {"label": "negative", "score": 0.8}}
    items = [{"title": "t1", "link": "old", "lang": "en"}, {"title": "t2", "link": "new", "lang": "en"},
             {"title": "t3", "link": "fr", "lang": "fr"}]
    sentiment.score_new(items, cache, clf=fake_clf)
    assert calls == [["t2"]]
    sentiment.attach(items, cache)
    assert [i["sentiment"] for i in items] == ["negative", "positive", None]
    avg = sentiment.average(items)
    assert avg["score"] == 0 and avg["n"] == 2   # (+1 - 1) / 2


# ---------------- store: a failure never produces numbers
def test_failure_envelope_has_no_data(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    assert store.run_dataset("x.json", "src", lambda: {"v": 1}) is True
    first = store.read("x.json")["_meta"]["last_success"]

    def boom():
        raise ConnectionError("HTTP 429 Too Many Requests")
    assert store.run_dataset("x.json", "src", boom) is False
    env = store.read("x.json")
    assert env["data"] is None
    assert env["_meta"]["status"] == "error"
    assert "429" in env["_meta"]["error"]
    assert env["_meta"]["last_success"] == first
