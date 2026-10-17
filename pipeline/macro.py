"""Macro data: FRED public CSV (no key) and the ECB Data Portal (no key)."""
import csv
import io
import time

import requests

from . import config

KEEP_FROM = "2010-01-01"
HEADERS = {
    # FRED tends to hang on bare script user-agents from cloud IPs
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36 AtlasTerminal",
    "Accept": "text/csv,text/plain,*/*",
}


def parse_fred_csv(text, series_id):
    """FRED CSV -> [(date, float)], '.' (no observation) skipped."""
    rows = list(csv.reader(io.StringIO(text)))
    if not rows or len(rows[0]) < 2:
        raise ValueError(f"unexpected FRED response for {series_id}")
    header = [h.strip() for h in rows[0]]
    if series_id not in header:
        raise ValueError(f"series {series_id} not found in FRED response header {header[:3]}")
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


def most_recent(candidates):
    """Pick the series whose last observation is the most recent (ECB keys get replaced over time)."""
    ok = [c for c in candidates if c[1]]
    if not ok:
        raise ValueError("no candidate series returned data")
    return max(ok, key=lambda c: c[1][-1][0])


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


def _get(url, attempts=3, timeout=60):
    last = None
    for i in range(attempts):
        try:
            r = requests.get(url, timeout=timeout, headers=HEADERS)
            r.raise_for_status()
            return r.text
        except Exception as e:  # noqa: BLE001
            last = e
            if i < attempts - 1:
                time.sleep(3 * (3 ** i))
    raise last


def _series(points, source):
    pts = [(d, v) for d, v in points if d >= KEEP_FROM]
    return {"dates": [d for d, _ in pts], "values": [round(v, 4) for _, v in pts],
            "latest": {"date": points[-1][0], "value": points[-1][1]}, "source": source}


def fetch_fred(series_id):
    url = config.FRED_URL.format(sid=series_id) + "&cosd=2008-01-01"
    pts = parse_fred_csv(_get(url), series_id)
    data = _series(pts, f"FRED {series_id}")
    if series_id == "CPIAUCSL":
        data["yoy"] = _series(yoy(pts), "FRED CPIAUCSL, computed YoY")
    return data


def _ecb_candidates(keys):
    out, errors = [], []
    for k in keys:
        try:
            out.append((k, parse_ecb_csv(_get(config.ECB_URL.format(key=k)))))
        except Exception as e:  # noqa: BLE001
            errors.append(f"{k}: {type(e).__name__}: {e}")
    if not out:
        raise RuntimeError("; ".join(errors))
    return out


def fetch_ecb_hicp():
    """Euro area HICP annual rate (%). The ECB replaced its ICP dataset by HICP in 2026."""
    key, pts = most_recent(_ecb_candidates(config.ECB_HICP_KEYS))
    return _series(pts, f"ECB {key}")


def fetch_ecb_deposit_rate():
    """ECB deposit facility rate (%), daily, from the ECB itself; FRED ECBDFR as fallback."""
    try:
        key, pts = most_recent(_ecb_candidates([config.ECB_DFR_KEY]))
        return _series(pts, f"ECB {key}")
    except Exception as ecb_err:  # noqa: BLE001
        try:
            return fetch_fred("ECBDFR")
        except Exception as fred_err:  # noqa: BLE001
            raise RuntimeError(f"ECB: {ecb_err} | FRED: {fred_err}") from fred_err
