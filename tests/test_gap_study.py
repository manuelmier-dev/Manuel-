import unittest

import numpy as np
import pandas as pd

from bot.gap_study import daily_table, gap_trades, report

NY = "America/New_York"


def make_bars(n_days=300, fade=True, seed=1):
    """Barras sintéticas de 24h con huecos nocturnos; con fade=True el precio devuelve parte del hueco entre 9:30 y 11:00."""
    rng = np.random.default_rng(seed)
    parts, px = [], 5000.0
    for d in pd.bdate_range("2022-01-03", periods=n_days):
        idx = pd.date_range(f"{d.date()} 09:30", f"{d.date()} 15:55", freq="5min", tz=NY)
        gap = rng.normal(0, 6)
        steps = rng.normal(0, 0.4, len(idx))
        open_px = px + gap
        if fade:
            steps[:18] += -np.sign(gap) * abs(gap) * 0.1 / 3          # devuelve parte del hueco en la primera hora y media
        close = open_px + np.cumsum(steps)
        opens = np.r_[open_px, close[:-1]]
        pre = pd.DataFrame({"open": px, "high": px, "low": px, "close": px, "volume": 1.0},
                           index=pd.DatetimeIndex([pd.Timestamp(f"{d.date()} 09:25", tz=NY)]))
        parts += [pre, pd.DataFrame({"open": opens, "high": np.maximum(opens, close) + 0.2, "low": np.minimum(opens, close) - 0.2,
                                     "close": close, "volume": 100.0}, index=idx)]
        px = close[-1]
    return pd.concat(parts)


class TestGapStudy(unittest.TestCase):
    def test_finds_planted_fade_and_no_effect_in_noise(self):
        r = report(make_bars(fade=True))["todo"]
        self.assertGreater(r["pts_bruto"], 0)
        self.assertLess(r["p_azar"], 0.01)
        n = report(make_bars(fade=False))["todo"]
        self.assertGreater(n["p_azar"], 0.01)

    def test_threshold_uses_only_previous_days_and_mirror_is_exact(self):
        t = daily_table(make_bars(n_days=60))
        self.assertTrue(np.isnan(t["atr20"].iloc[0]))
        self.assertAlmostEqual(t["atr20"].iloc[25], t["range"].iloc[5:25].mean())          # días 5..24, nunca el propio día
        tr = gap_trades(t)
        self.assertTrue((tr["fade_pts"] == -np.sign(tr["gap"]) * tr["x"]).all())


if __name__ == "__main__":
    unittest.main()
