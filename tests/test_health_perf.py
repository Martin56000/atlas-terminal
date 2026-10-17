"""Autonomy: health checks, alerts, failure tracking; performance horizons; calendars stay current."""
from datetime import date, datetime, timedelta, timezone

import pytest

from pipeline import health, metrics, store

UTC = timezone.utc


def test_perf_stats_hand_example():
    # 300 sessions; closes 100, 101, ... ; last year ends at index 259
    dates = [(date(2025, 3, 15) + timedelta(days=i)).isoformat() for i in range(300)]   # crosses into 2026
    closes = [100.0 + i for i in range(300)]
    p = metrics.perf_stats(dates, closes)
    assert p["w1"] == pytest.approx(399 / 394 - 1)      # 5 sessions back
    assert p["m1"] == pytest.approx(399 / 378 - 1)      # 21 sessions back
    assert p["y1"] == pytest.approx(399 / 147 - 1)      # 252 sessions back
    last_2025 = max(i for i, d in enumerate(dates) if d < "2026")
    assert p["ytd"] == pytest.approx(399 / closes[last_2025] - 1)
    assert (p["hi52"], p["lo52"]) == (399, 148)
    short = metrics.perf_stats(dates[:3], closes[:3])
    assert short["m1"] is None and short["y1"] is None   # not enough history: never extrapolated


def test_allowed_age_covers_weekends():
    tue = datetime(2026, 10, 20, 12, 0, tzinfo=UTC)
    sun = datetime(2026, 10, 18, 12, 0, tzinfo=UTC)
    mon_early = datetime(2026, 10, 19, 6, 0, tzinfo=UTC)      # 08:00 Paris
    assert health.allowed_hours(30, tue) == 30
    assert health.allowed_hours(30, sun) == 102
    assert health.allowed_hours(30, mon_early) == 102


def test_fail_since_tracking():
    st = {}
    health.update_fail_since(st, "ROG.SW", True, "empty", "2026-10-14T10:00:00+00:00")
    health.update_fail_since(st, "ROG.SW", True, "still empty", "2026-10-15T10:00:00+00:00")
    assert st["fail_since"]["ROG.SW"] == {"since": "2026-10-14T10:00:00+00:00", "error": "still empty"}   # first failure kept
    health.update_fail_since(st, "ROG.SW", False, None, "2026-10-16T10:00:00+00:00")
    assert "ROG.SW" not in st["fail_since"]


def _env(ts, status="ok"):
    return {"_meta": {"fetched_at": ts, "status": status, "last_success": ts if status == "ok" else None, "source": "s"}, "data": {}}


def test_compute_flags_stale_sources_and_long_failures(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    now = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)          # Wednesday
    fresh = (now - timedelta(hours=2)).isoformat()
    for name in health.DATASETS:
        store.write(name, _env(fresh))
    store.write("macro.json", _env((now - timedelta(hours=50)).isoformat()))      # 50 h old on a weekday
    store.write("state.json", {"fail_since": {"ROG.SW": {"since": (now - timedelta(days=4)).isoformat(), "error": "empty"},
                                              "FDJU.PA": {"since": (now - timedelta(hours=5)).isoformat(), "error": "x"}}})
    st = health.compute(now)
    assert any("Macro" in p for p in st["problems"])
    assert any("ROG.SW" in p and "FDJU.PA" not in p for p in st["problems"])
    assert [r["ok"] for r in st["datasets"] if r["name"] == "quotes.json"] == [True]


def test_issue_opened_then_closed(monkeypatch):
    calls = []

    def fake_gh(method, path, token, body=None):
        calls.append((method, path, body))
        if method == "GET":
            return fake_gh.open
        return {}
    monkeypatch.setattr(health, "_gh", fake_gh)
    fake_gh.open = []
    health.sync_issue({"problems": ["Macro : pas de mise à jour"]}, "o/r", "tok", "o")
    assert calls[-1][0] == "POST" and calls[-1][2]["assignees"] == ["o"] and "Macro" in calls[-1][2]["body"]
    calls.clear()
    fake_gh.open = [{"number": 7}]
    health.sync_issue({"problems": []}, "o/r", "tok", "o")
    assert ("PATCH", "/repos/o/r/issues/7", {"state": "closed"}) in calls


def test_market_calendars_know_the_coming_year():
    import exchange_calendars as xcals
    import pandas as pd
    horizon = pd.Timestamp.now().normalize() + pd.Timedelta(days=300)
    for ex in ("XNYS", "XPAR", "XETR", "XLON"):
        assert xcals.get_calendar(ex).last_session >= horizon, ex


def test_translation_never_changes_a_number():
    from pipeline import translate
    assert translate.numbers_ok("LVMH was founded in 1765", "LVMH a été fondée en 1765")
    assert not translate.numbers_ok("LVMH was founded in 1765", "LVMH a été fondée en 1365")   # real model error
    assert translate.numbers_ok("Sales up 3.5% to $1,234m", "Ventes en hausse de 3,5 % à 1 234 M$")
    assert not translate.numbers_ok("Q3 sales up 12%", "Ventes en hausse de 12 %")             # a number dropped

    def fake(sents, **k):
        return [{"translation_text": {"It was founded in 1765.": "Elle a été fondée en 1365.",
                                      "It sells wine.": "Elle vend du vin."}[s]} for s in sents]
    out = translate.translate_text("It sells wine. It was founded in 1765.", tr=fake)
    assert out == "Elle vend du vin. It was founded in 1765."      # the bad sentence stays in English
    cache = translate.translate_new([{"lang": "en", "link": "l", "title": "Q3 up 12%"}], {},
                                    tr=lambda xs, **k: [{"translation_text": "Hausse au T3"}])
    assert cache == {"l": ""}
    h = translate.attach([{"lang": "en", "link": "l", "title": "Q3 up 12%"}], cache)
    assert h[0]["title_fr"] is None


def test_rotation_refetches_pages_missing_a_new_field(tmp_path, monkeypatch):
    from pipeline import run
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    fresh = datetime.now(UTC).isoformat()
    store.write("company/A.json", {"_meta": {"status": "ok", "fetched_at": fresh}, "data": {"profile": {}}})
    store.write("company/B.json", {"_meta": {"status": "ok", "fetched_at": fresh}, "data": {"dividends": []}})
    assert run.rotation("company", ["A", "B"], 10, 20, required=("dividends",)) == ["A"]
