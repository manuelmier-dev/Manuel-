import unittest
from datetime import date, time

import numpy as np
import pandas as pd

from bot.backtest import run_backtest, skip_reason
from bot.config import Params
from bot.gex import expected_move, gamma_exposure
from bot.indicators import add_indicators, rsi
from bot.validate import validate_bars, validate_days

NY = "America/New_York"


class TestGex(unittest.TestCase):
    def test_gex_values_and_walls(self):
        chain = pd.DataFrame({
            "strike": [5050, 4950], "right": ["C", "P"],
            "gamma": [0.01, 0.02], "open_interest": [1000, 500]})
        g = gamma_exposure(chain, spot=5000)
        # 0.01*1000*100*5000^2*0.01 = 2.5e8 ; la put iguala -> total 0
        self.assertAlmostEqual(g["total_bn"], 0.0, places=9)
        self.assertEqual(g["call_wall"], 5050)
        self.assertEqual(g["put_wall"], 4950)

    def test_gex_positive_when_calls_dominate(self):
        chain = pd.DataFrame({"strike": [5050, 4950], "right": ["C", "P"],
                              "gamma": [0.02, 0.01], "open_interest": [1000, 500]})
        self.assertAlmostEqual(gamma_exposure(chain, 5000)["total_bn"], 0.375, places=6)   # (0.02*1000 - 0.01*500)*100*5000^2*0.01 = 3.75e8

    def test_expected_move_is_atm_straddle(self):
        q = pd.DataFrame({"strike": [4995, 4995, 5000, 5000, 5005, 5005],
                          "right": ["C", "P"] * 3, "mid": [12, 8, 9, 10, 7, 13]})
        self.assertEqual(expected_move(q, spot=5001), 19.0)


class TestIndicators(unittest.TestCase):
    def test_rsi_extremes(self):
        up = pd.Series(np.arange(1.0, 40.0))
        self.assertAlmostEqual(rsi(up, 14).iloc[-1], 100.0)
        self.assertAlmostEqual(rsi(-up, 14).iloc[-1], 0.0, places=6)
        self.assertEqual(rsi(pd.Series([5.0] * 30), 14).iloc[-1], 50.0)

    def test_vwap_constant_price(self):
        idx = pd.date_range("2024-01-02 09:30", periods=10, freq="5min", tz=NY)
        b = pd.DataFrame({"open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0, "volume": 10.0}, index=idx)
        out = add_indicators(b, Params())
        self.assertTrue((out["vwap"] == 100.0).all())


class TestValidation(unittest.TestCase):
    def _days(self, oi):
        return pd.DataFrame({"gex_bn": [1.0], "em_pts": [40.0], "call_wall": [5040.0],
                             "put_wall": [4960.0], "basis": [0.0], "oi_date": [oi]},
                            index=[date(2024, 1, 3)])

    def test_rejects_same_day_open_interest(self):
        self.assertTrue(validate_days(self._days(date(2024, 1, 3))))
        with self.assertRaises(ValueError):
            run_backtest(pd.DataFrame(), self._days(date(2024, 1, 3)))

    def test_accepts_previous_day_open_interest(self):
        self.assertEqual(validate_days(self._days(date(2024, 1, 2))), [])

    def test_bars_need_timezone(self):
        idx = pd.date_range("2024-01-02 09:30", periods=3, freq="5min")
        b = pd.DataFrame({"open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 1.0}, index=idx)
        self.assertTrue(validate_bars(b))


class TestDayFilter(unittest.TestCase):
    def test_filters(self):
        p = Params()
        ok = pd.Series({"gex_bn": 1.0, "em_pts": 40.0})
        self.assertIsNone(skip_reason(ok, p))
        self.assertIsNotNone(skip_reason(pd.Series({"gex_bn": -2.0, "em_pts": 40.0}), p))
        self.assertIsNotNone(skip_reason(pd.Series({"gex_bn": 0.3, "em_pts": 40.0}), p))
        self.assertIsNotNone(skip_reason(pd.Series({"gex_bn": 1.0, "em_pts": 15.0}), p))


def scenario(path_after_ramp):
    """Día de prueba armado a mano: base plana en 5000, sube al call wall (5040), luego sigue 'path_after_ramp'."""
    idx = pd.date_range("2024-01-03 09:30", "2024-01-03 15:55", freq="5min", tz=NY)
    n = len(idx)
    closes = np.full(n, 5000.0)
    ramp = [5010, 5020, 5030, 5038, 5040]
    start = 22
    closes[start:start + len(ramp)] = ramp
    tail = np.array(path_after_ramp, dtype=float)
    closes[start + len(ramp):start + len(ramp) + len(tail)] = tail
    closes[start + len(ramp) + len(tail):] = tail[-1]
    open_ = np.r_[5000.0, closes[:-1]]
    b = pd.DataFrame({"open": open_, "high": np.maximum(open_, closes), "low": np.minimum(open_, closes),
                      "close": closes, "volume": 1000.0}, index=idx)
    days = pd.DataFrame({"gex_bn": [1.0], "em_pts": [40.0], "call_wall": [5040.0], "put_wall": [4960.0],
                         "basis": [0.0], "oi_date": [date(2024, 1, 2)]}, index=[date(2024, 1, 3)])
    return b, days


P = Params(entry_end=time(12, 0), reentry_end=time(13, 0), confirmations_required=1, slippage_pts=0.0, commission_rt=0.0)


class TestBacktest(unittest.TestCase):
    def test_short_hits_target(self):
        b, d = scenario([5030, 5015, 5004, 5000])
        trades, _ = run_backtest(b, d, P)
        self.assertEqual(len(trades), 1)
        t = trades.iloc[0]
        self.assertEqual((t["side"], t["reason"]), ("short", "target"))
        self.assertAlmostEqual(t["stop"] - t["entry"], 8.0)        # 20% de 40
        self.assertAlmostEqual(t["entry"] - t["target"], 36.0)     # 90% de 40
        self.assertGreater(t["usd"], 0)

    def test_short_stops_out_and_never_exceeds_two_entries(self):
        b, d = scenario([5050, 5060, 5070, 5080])
        trades, _ = run_backtest(b, d, P)
        self.assertGreaterEqual(len(trades), 1)
        self.assertLessEqual(len(trades), 2)
        self.assertEqual(trades.iloc[0]["reason"], "stop")
        self.assertLess(trades.iloc[0]["usd"], 0)
        if len(trades) == 2:
            self.assertEqual(trades.iloc[1]["n"], 2)

    def test_no_trade_when_gamma_negative(self):
        b, d = scenario([5030, 5015, 5004, 5000])
        d["gex_bn"] = -1.0
        trades, skipped = run_backtest(b, d, P)
        self.assertTrue(trades.empty)
        self.assertEqual(skipped.iloc[0]["reason"], "gamma_negativo_o_choppy")

    def test_entry_uses_next_bar_open_not_signal_bar(self):
        b, d = scenario([5030, 5015, 5004, 5000])
        trades, _ = run_backtest(b, d, P)
        t = trades.iloc[0]
        first_touch = b.index[b["high"] >= 5036].min()        # zona = 5040 - 10% de 40
        self.assertGreater(t["entry_time"], first_touch)       # entra DESPUÉS de la barra de la señal
        self.assertEqual(t["entry"], b.loc[t["entry_time"], "open"])


if __name__ == "__main__":
    unittest.main()
