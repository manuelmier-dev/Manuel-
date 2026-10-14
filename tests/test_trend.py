import unittest

import numpy as np
import pandas as pd

from bot.config import Params
from bot.trend import OrbParams, run_orb

NY = "America/New_York"


def day(breakout=None):
    """Día de prueba: primera hora entre 4990 y 5010; luego plano en 5000 o ruptura 'up'/'down' a partir de las 10:40."""
    idx = pd.date_range("2026-10-13 09:30", "2026-10-13 15:55", freq="5min", tz=NY)
    px = np.full(len(idx), 5000.0)
    hi = px + 0.5
    lo = px - 0.5
    first = [i for i, t in enumerate(idx) if t.hour == 9 or (t.hour == 10 and t.minute < 30)]
    hi[first[3]], lo[first[6]] = 5010.0, 4990.0
    if breakout:
        start = [i for i, t in enumerate(idx) if t.hour == 10 and t.minute == 40][0]
        for k in range(start, len(idx)):
            step = 6.0 * (k - start + 1)
            px[k] = 5000 + (step if breakout == "up" else -step)
            hi[k], lo[k] = px[k] + 0.5, px[k] - 0.5
    open_ = np.r_[5000.0, px[:-1]]
    b = pd.DataFrame({"open": open_, "high": np.maximum(hi, np.maximum(open_, px)), "low": np.minimum(lo, np.minimum(open_, px)),
                      "close": px, "volume": 1000.0}, index=idx)
    d = pd.DataFrame({"gex_bn": [-3.0], "em_pts": [40.0]}, index=[pd.Timestamp("2026-10-13").date()])
    return b, d


class TestOrb(unittest.TestCase):
    P = Params(slippage_pts=0.0, commission_rt=0.0)

    def test_upward_breakout_goes_long_and_hits_target(self):
        b, d = day("up")
        t = run_orb(b, d, self.P, OrbParams(target_em=0.5))
        self.assertEqual(len(t), 1)
        self.assertEqual((t.iloc[0]["side"], t.iloc[0]["reason"]), ("long", "target"))
        self.assertGreater(t.iloc[0]["usd"], 0)

    def test_downward_breakout_goes_short(self):
        b, d = day("down")
        t = run_orb(b, d, self.P, OrbParams(target_em=0.5))
        self.assertEqual(t.iloc[0]["side"], "short")

    def test_no_breakout_no_trade(self):
        b, d = day(None)
        self.assertTrue(run_orb(b, d, self.P).empty)

    def test_positive_gamma_day_is_not_traded(self):
        b, d = day("up")
        d["gex_bn"] = 2.0
        self.assertTrue(run_orb(b, d, self.P).empty)

    def test_stop_is_between_the_limits(self):
        b, d = day("up")
        t = run_orb(b, d, self.P, OrbParams(target_em=0.5)).iloc[0]
        dist = t["entry"] - t["stop"]
        self.assertGreaterEqual(dist, 0.2 * 40 - 1e-9)
        self.assertLessEqual(dist, 0.8 * 40 + 1e-9)


if __name__ == "__main__":
    unittest.main()
