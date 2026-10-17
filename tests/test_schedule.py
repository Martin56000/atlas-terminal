"""Update schedule. Dates are real calendar days in late October 2026, including the
week when Paris has changed to winter time but New York has not yet."""
from datetime import datetime
from zoneinfo import ZoneInfo

from pipeline.schedule import decide

P = ZoneInfo("Europe/Paris")
UTC = ZoneInfo("UTC")


def at(y, mo, d, h, mi):
    return datetime(y, mo, d, h, mi, tzinfo=P).astimezone(UTC)


DONE = {"daily": "2026-10-19", "eu_close": None, "news_at": None}


def test_daily_batch_0830_once():
    assert "daily" in decide(at(2026, 10, 19, 8, 35), {"daily": "2026-10-16"})
    assert "daily" not in decide(at(2026, 10, 19, 9, 5), {"daily": "2026-10-19"})
    assert "daily" not in decide(at(2026, 10, 19, 8, 15), {"daily": "2026-10-16"})


def test_morning_only_europe():
    tasks = decide(at(2026, 10, 19, 10, 0), DONE)
    assert "quotes_eu" in tasks and "quotes_us" not in tasks and "news" in tasks


def test_afternoon_both_markets():
    tasks = decide(at(2026, 10, 19, 16, 0), DONE)       # 10:00 in New York
    assert "quotes_us" in tasks and "quotes_eu" in tasks


def test_eu_close_run_and_day_end():
    tasks = decide(at(2026, 10, 19, 17, 45), DONE)
    assert "eu_close" in tasks and "quotes_us" in tasks
    assert decide(at(2026, 10, 19, 19, 0), {**DONE, "eu_close": "2026-10-19",
                                              "news_at": "2026-10-19T16:30:00+00:00"}) == []


def test_dst_gap_week_us_opens_1430_paris():
    # Tue 27 Oct 2026: Paris is UTC+1, New York still UTC-4 -> NYSE opens 14:30 Paris
    s = {"daily": "2026-10-27", "eu_close": None, "news_at": None}
    assert "quotes_us" in decide(at(2026, 10, 27, 14, 45), s)
    # Tue 3 Nov 2026: both on winter time -> opens 15:30 Paris
    s = {"daily": "2026-11-03", "eu_close": None, "news_at": None}
    assert "quotes_us" not in decide(at(2026, 11, 3, 14, 45), s)
    assert "quotes_us" in decide(at(2026, 11, 3, 15, 45), s)


def test_weekend_and_holiday():
    assert decide(at(2026, 10, 17, 12, 0), {"daily": "2026-10-16"}) == []          # Saturday
    tasks = decide(at(2026, 12, 25, 16, 0), {"daily": "2026-12-25", "news_at": None})  # Christmas
    assert "quotes_us" not in tasks and "quotes_eu" not in tasks


def test_news_hourly():
    s = {"daily": "2026-10-19", "news_at": at(2026, 10, 19, 10, 0).isoformat()}
    assert "news" not in decide(at(2026, 10, 19, 10, 30), s)
    assert "news" in decide(at(2026, 10, 19, 11, 0), s)


def test_force_runs_everything():
    assert decide(at(2026, 10, 17, 3, 0), {}, force=True) == ["daily", "quotes_us", "quotes_eu", "news"]
