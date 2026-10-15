import unittest

import numpy as np
import pandas as pd

from bot.hyp_test import COST_PTS, day_features, evaluate, rule_returns

NY = "America/New_York"


def make_bars(n_days=120, momentum=True, seed=0):
    """Días sintéticos de 9:00 a 15:55. Con momentum=True el último tramo (15:30-15:55) sigue la dirección de la primera media hora."""
    rng = np.random.default_rng(seed)
    parts, px = [], 5000.0
    for d in pd.bdate_range("2023-01-02", periods=n_days):
        idx = pd.date_range(f"{d.date()} 09:00", f"{d.date()} 15:55", freq="5min", tz=NY)
        steps = rng.normal(0, 0.5, len(idx))
        first = rng.normal(0, 3)
        i0 = [i for i, t in enumerate(idx) if t.strftime("%H:%M") == "09:30"][0]
        steps[i0:i0 + 6] += first / 6                                # primera media hora con dirección
        if momentum:
            i1 = [i for i, t in enumerate(idx) if t.strftime("%H:%M") == "15:30"][0]
            steps[i1:] += np.sign(first) * 0.8                        # la última media hora sigue esa dirección
        close = px + np.cumsum(steps)
        open_ = np.r_[px, close[:-1]]
        px = close[-1]
        parts.append(pd.DataFrame({"open": open_, "high": np.maximum(open_, close) + 0.1, "low": np.minimum(open_, close) - 0.1,
                                   "close": close, "volume": 100.0}, index=idx))
    return pd.concat(parts)


class TestHypTest(unittest.TestCase):
    def run_eval(self, momentum):
        bars = make_bars(momentum=momentum)
        f = day_features(bars)
        em = pd.Series(20.0, index=f.index)
        gex = pd.Series(np.where(np.arange(len(f)) % 2 == 0, 1.0, -1.0), index=f.index)
        return evaluate(rule_returns(f, em), gex, "2023-05-01", n_perm=300).set_index("regla")

    def test_detects_planted_momentum_and_not_in_pure_noise(self):
        with_m = self.run_eval(True)
        self.assertLess(with_m.loc["M1", "p_azar"], 0.01)
        self.assertGreater(with_m.loc["M1", "pts_neto"], 0)
        noise = self.run_eval(False)
        self.assertGreater(noise.loc["M1", "p_azar"], 0.01)

    def test_costs_are_subtracted(self):
        self.assertAlmostEqual(COST_PTS, 0.58)
        r = self.run_eval(True)
        self.assertAlmostEqual(r.loc["M1", "pts_bruto"] - r.loc["M1", "pts_neto"], COST_PTS, places=2)

    def test_features_are_taken_from_the_right_bars(self):
        bars = make_bars(n_days=3)
        f = day_features(bars)
        d = f.index[1]
        g = bars[bars.index.date == d]
        self.assertAlmostEqual(f.loc[d, "open"], g.loc[[t for t in g.index if t.strftime("%H:%M") == "09:30"][0], "open"])
        self.assertAlmostEqual(f.loc[d, "prev_close"], f.iloc[0]["close"])


if __name__ == "__main__":
    unittest.main()
