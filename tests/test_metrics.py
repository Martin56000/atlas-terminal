"""Risk metrics on tiny hand-calculated examples."""
import math

import pandas as pd
import pytest

from pipeline import metrics as m


def s(values, start="2024-01-01"):
    return pd.Series(values, index=pd.bdate_range(start, periods=len(values)), dtype=float)


def test_log_returns():
    # P = 100 -> 110 -> 99 : r = ln(1.1), ln(0.9)
    r = m.log_returns(s([100, 110, 99]))
    assert r.tolist() == pytest.approx([math.log(1.1), math.log(0.9)])


def test_annualized_volatility_hand_example():
    # P = 100, 200, 100 -> r = [ln2, -ln2], mean 0
    # sample variance = (ln2^2 + ln2^2) / (2-1) = 2 ln2^2  -> std = sqrt(2) ln2 = 0.980258
    # annualized = 0.980258 * sqrt(252) = 15.5612
    r = m.log_returns(s([100, 200, 100]))
    assert m.annualized_volatility(r) == pytest.approx(math.sqrt(2) * math.log(2) * math.sqrt(252))
    assert m.annualized_volatility(r) == pytest.approx(15.5612, abs=1e-4)


def test_annualized_return_hand_example():
    # one return ln(1.1) = 0.0953102 ; * 252 = 24.01817
    r = m.log_returns(s([100, 110]))
    assert m.annualized_return(r) == pytest.approx(24.01817, abs=1e-5)
    # P = 100, 200, 100 -> mean 0 -> annualized return 0
    assert m.annualized_return(m.log_returns(s([100, 200, 100]))) == pytest.approx(0.0)


def test_sharpe():
    assert m.sharpe_ratio(0.10, 0.20, 0.04) == pytest.approx(0.30)   # (0.10-0.04)/0.20
    assert m.sharpe_ratio(-0.05, 0.25, 0.05) == pytest.approx(-0.40)  # (-0.05-0.05)/0.25
    assert m.sharpe_ratio(0.10, 0.0, 0.04) is None                    # undefined, never invented


def test_beta_two_times_benchmark():
    # benchmark 100,110,99,108.9 ; stock = 100*(bench/100)^2 -> r_stock = 2 r_bench -> beta = 2
    b = s([100, 110, 99, 108.9])
    st = s([100, 121, 98.01, 118.5921])
    assert m.beta(m.log_returns(st), m.log_returns(b)) == pytest.approx(2.0)


def test_beta_aligns_dates():
    b = m.log_returns(s([100, 110, 99, 108.9, 98.01]))
    st = m.log_returns(s([100, 121, 98.01, 118.5921, 96.059601]))
    # remove one date from the stock: inner join on the 3 common dates must still give beta 2
    assert m.beta(st.drop(st.index[1]), b) == pytest.approx(2.0)


def test_max_drawdown_hand_example():
    # peaks 120 then 130 ; troughs 90 (-25%) then 65 (-50%) -> MDD = -50%
    assert m.max_drawdown(s([100, 120, 90, 130, 65])) == pytest.approx(-0.50)
    assert m.max_drawdown(s([100, 101, 102])) == pytest.approx(0.0)


def test_window_uses_last_252_returns():
    p = s([100 + i for i in range(300)])
    w = m.window_prices(p, 252)
    assert len(w) == 253 and len(m.log_returns(w)) == 252
    assert w.iloc[-1] == 399


def test_correlation_matrix():
    a = m.log_returns(s([100, 110, 99, 108.9]))
    c = m.correlation_matrix({"A": a, "B": 2 * a, "C": -a})
    assert c.loc["A", "B"] == pytest.approx(1.0)
    assert c.loc["A", "C"] == pytest.approx(-1.0)


def test_risk_metrics_combined():
    # window=2 keeps the last 3 prices: 200, 100, 200 -> r = [-ln2, ln2]
    p = s([50, 200, 100, 200])
    bench = s([50, 200, 100, 200])
    out = m.risk_metrics(p, bench, rf=0.03, window=2)
    assert out["n_returns"] == 2
    assert out["ann_return"] == pytest.approx(0.0)
    assert out["ann_vol"] == pytest.approx(math.sqrt(2) * math.log(2) * math.sqrt(252))
    assert out["sharpe"] == pytest.approx(-0.03 / out["ann_vol"])
    assert out["beta"] == pytest.approx(1.0)
    assert out["max_drawdown"] == pytest.approx(-0.50)
