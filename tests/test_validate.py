"""Cross-check must compare the same session on both sides and ignore Yahoo rows with an empty close."""
import sys
import types

import pandas as pd

from pipeline import store, validate


def test_cross_check_ignores_empty_latest_close(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    dates = pd.bdate_range("2025-09-01", periods=300)
    closes = [100 + (i % 7) for i in range(300)]
    for t in validate.CHECK:
        store.write(f"history/{t}.json", {"_meta": {"status": "ok"}, "data": {
            "dates": [d.strftime("%Y-%m-%d") for d in dates], "close": closes, "currency": "USD"}})
    adj = pd.Series(closes, dtype=float)
    vol, _ = validate.manual_vol(adj.tolist())
    store.write("risk.json", {"data": {"metrics": {t: {"ann_vol": vol} for t in validate.CHECK}}})
    # Yahoo returns one more session whose close is still empty
    idx = list(dates) + [dates[-1] + pd.offsets.BDay(1)]
    df = pd.DataFrame({"Close": closes + [float("nan")], "Adj Close": closes + [float("nan")]},
                      index=pd.DatetimeIndex(idx).tz_localize("UTC"))

    class T:
        def __init__(self, t):
            pass

        def history(self, **kw):
            return df.copy()
    monkeypatch.setitem(sys.modules, "yfinance", types.SimpleNamespace(Ticker=T))
    monkeypatch.setattr(validate, "completed_bars", lambda f, ex: f)
    out = validate.run()
    assert out["all_passed"], out
    assert out["checks"][1]["date"] == dates[-1].strftime("%Y-%m-%d")
