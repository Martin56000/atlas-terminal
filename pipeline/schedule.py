"""Decide what an update run should do, from the current time and the last runs.

GitHub's scheduler fires every 15 minutes on weekdays but can be late or skip a
tick, so every rule is "window + not done yet" rather than an exact minute."""
from datetime import datetime, time as dtime, timedelta, timezone
from zoneinfo import ZoneInfo

import exchange_calendars as xcals
import pandas as pd

from . import config

PARIS = ZoneInfo(config.PARIS)
EU_EXCHANGES = sorted({t["exchange"] for t in config.EU_STOCKS + config.EU_INDICES})
QUOTE_GRACE = timedelta(minutes=20)  # one run just after the close captures the closing print


def _hm(s):
    h, m = s.split(":")
    return dtime(int(h), int(m))


def exchange_open(exchange, now_utc, grace=timedelta(0)):
    cal = xcals.get_calendar(exchange)
    ts = pd.Timestamp(now_utc)
    day = ts.tz_convert(cal.tz).normalize().tz_localize(None)
    if not cal.is_session(day):
        return False
    return cal.session_open(day) <= ts <= cal.session_close(day) + grace


def any_session_today(exchanges, now_utc):
    for ex in exchanges:
        cal = xcals.get_calendar(ex)
        day = pd.Timestamp(now_utc).tz_convert(cal.tz).normalize().tz_localize(None)
        if cal.is_session(day):
            return True
    return False


def decide(now_utc: datetime, state: dict, force=False):
    """Return the ordered list of tasks to run now."""
    if force:
        return ["daily", "quotes_us", "quotes_eu", "news"]
    paris = now_utc.astimezone(PARIS)
    today = paris.date().isoformat()
    if paris.weekday() >= 5:
        return []
    t = paris.time()
    tasks = []
    first_run = not state.get("daily")
    if first_run or (t >= _hm(config.DAILY_BATCH_AT) and state.get("daily") != today):
        tasks.append("daily")
    before_day_end = t <= _hm(config.OWNER_DAY_END)
    if before_day_end and exchange_open("XNYS", now_utc, QUOTE_GRACE):
        tasks.append("quotes_us")
    if before_day_end and any(exchange_open(ex, now_utc, QUOTE_GRACE) for ex in EU_EXCHANGES):
        tasks.append("quotes_eu")
    if (t >= _hm(config.EU_CLOSE_RUN_AT) and state.get("eu_close") != today
            and any_session_today(EU_EXCHANGES, now_utc) and "daily" not in tasks):
        tasks.append("eu_close")
    if _hm(config.NEWS_START) <= t <= _hm(config.OWNER_DAY_END):
        last = state.get("news_at")
        if not last or (now_utc - datetime.fromisoformat(last)) >= timedelta(minutes=config.NEWS_EVERY_MIN):
            tasks.append("news")
    return tasks


def sessions_json(now_utc: datetime, days_back=10, days_fwd=7):
    """Session open/close times per exchange so the site can tell if a market is open
    (and whether data is stale) without a server."""
    out = {}
    start = (pd.Timestamp(now_utc) - pd.Timedelta(days=days_back)).tz_localize(None).normalize()
    end = (pd.Timestamp(now_utc) + pd.Timedelta(days=days_fwd)).tz_localize(None).normalize()
    for ex in ["XNYS"] + EU_EXCHANGES:
        cal = xcals.get_calendar(ex)
        sched = cal.schedule.loc[start:end]
        out[ex] = [[o.isoformat(), c.isoformat()] for o, c in zip(sched["open"], sched["close"])]
    return out


def utcnow():
    return datetime.now(timezone.utc)
