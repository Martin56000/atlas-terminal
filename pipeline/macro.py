"""Macro data: FRED public CSV (no key) and the ECB Data Portal (no key)."""
import csv
import io

import requests

from . import config

KEEP_FROM = "2010-01-01"


def parse_fred_csv(text, series_id):
    """FRED CSV -> [(date, float)], '.' (no observation) skipped."""
    rows = list(csv.reader(io.StringIO(text)))
    if not rows or len(rows[0]) < 2:
        raise ValueError(f"unexpected FRED response for {series_id}")
    header = [h.strip() for h in rows[0]]
    if series_id not in header:
        raise ValueError(f"series {series_id} not found in FRED response header {header}")
    vi = header.index(series_id)
    out = []
    for r in rows[1:]:
        if len(r) <= vi:
            continue
        v = r[vi].strip()
        if v in ("", "."):
            continue
        out.append((r[0].strip(), float(v)))
    if not out:
        raise ValueError(f"no observations for {series_id}")
    return out


def parse_ecb_csv(text):
    rows = list(csv.DictReader(io.StringIO(text)))
    if not rows or "TIME_PERIOD" not in rows[0] or "OBS_VALUE" not in rows[0]:
        raise ValueError("unexpected ECB response (TIME_PERIOD / OBS_VALUE missing)")
    out = [(r["TIME_PERIOD"], float(r["OBS_VALUE"])) for r in rows if r.get("OBS_VALUE") not in (None, "", "NaN")]
    out.sort()
    if not out:
        raise ValueError("no ECB observations")
    return out


def yoy(points):
    """Monthly index -> year-over-year % change: X_t / X_{t-12} - 1 (in %)."""
    by_date = dict(points)
    dates = [d for d, _ in points]
    out = []
    for i, d in enumerate(dates):
        if i >= 12:
            prev = by_date[dates[i - 12]]
            # guard: the observation 12 rows earlier must be exactly 1 year earlier
            if dates[i - 12][:4] == str(int(d[:4]) - 1) and dates[i - 12][5:7] == d[5:7]:
                out.append((d, (by_date[d] / prev - 1) * 100))
    return out


def _get(url):
    r = requests.get(url, timeout=30, headers={"User-Agent": "Atlas Terminal (student project)"})
    r.raise_for_status()
    return r.text


def _series(points):
    pts = [(d, v) for d, v in points if d >= KEEP_FROM]
    return {"dates": [d for d, _ in pts], "values": [round(v, 4) for _, v in pts],
            "latest": {"date": points[-1][0], "value": points[-1][1]}}


def fetch_fred(series_id):
    pts = parse_fred_csv(_get(config.FRED_URL.format(sid=series_id)), series_id)
    data = _series(pts)
    if series_id == "CPIAUCSL":
        data["yoy"] = _series(yoy(pts))
    return data


def fetch_ecb_hicp():
    # Series already is the annual rate of change (%), monthly.
    return _series(parse_ecb_csv(_get(config.ECB_HICP_URL)))
