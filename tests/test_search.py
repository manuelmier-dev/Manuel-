import unittest

import numpy as np
import pandas as pd

from bot.search import EXITS, TIMES, build, masks_for, null_runs, pick, search, stat
from bot.strategy_m import add_manuel_indicators

NY = "America/New_York"


def synth(step=6, seed=0):
    """Barras de 24 h de 5 minutos con un paseo al azar, un día de cada `step` días hábiles entre 2012 y 2026 (para tener entrenamiento, validación y prueba)."""
    rng = np.random.default_rng(seed)
    parts, px = [], 5000.0
    for d in pd.bdate_range("2012-01-02", "2026-06-30")[::step]:
        idx = pd.date_range(f"{(d - pd.Timedelta(days=1)).date()} 18:00", f"{d.date()} 15:55", freq="5min", tz=NY)
        steps = rng.normal(0, 0.5, len(idx))
        close = px + np.cumsum(steps)
        opens = np.r_[px, close[:-1]]
        parts.append(pd.DataFrame({"open": opens, "high": np.maximum(opens, close) + 0.2, "low": np.minimum(opens, close) - 0.2, "close": close, "volume": 100.0}, index=idx))
        px = close[-1]
    out = pd.concat(parts)
    return out[~out.index.duplicated(keep="last")]


class TestSearch(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.df = add_manuel_indicators(synth())
        cls.data = build(cls.df)

    def test_matrices_have_all_exits_and_sides(self):
        td = self.data["T"]["10:00"]
        for e in EXITS:
            self.assertIn((e, "L"), td["res"])
            self.assertIn((e, "S"), td["res"])
        self.assertEqual(set(self.data["T"]), set(TIMES))

    def test_horizon_return_matches_manual_calculation(self):
        days = self.data["days"]
        i = 30
        d = days[i]
        j = self.df.index.get_loc(pd.Timestamp(f"{d.date()} 10:00", tz=NY))
        manual = self.df.iloc[j + 5]["close"] - self.df.iloc[j]["open"]                    # 30 min = 6 barras: la sexta cierra en j+5
        self.assertAlmostEqual(self.data["T"]["10:00"]["res"][("30m", "L")][i], manual)
        self.assertAlmostEqual(self.data["T"]["10:00"]["res"][("30m", "S")][i], -manual)
        close_day = self.df.loc[pd.Timestamp(f"{d.date()} 15:55", tz=NY), "close"]
        self.assertAlmostEqual(self.data["T"]["10:00"]["res"][("cierre", "L")][i], close_day - self.df.iloc[j]["open"])

    def test_stop_hits_first_when_both_touch_in_the_same_bar(self):
        df = self.df.copy()
        d = self.data["days"][20]
        j = df.index.get_loc(pd.Timestamp(f"{d.date()} 12:00", tz=NY))
        atr = self.data["atr"][20]
        df.iloc[j, df.columns.get_loc("high")] = df.iloc[j]["open"] + 10 * atr          # la misma barra toca objetivo y stop
        df.iloc[j, df.columns.get_loc("low")] = df.iloc[j]["open"] - 10 * atr
        r = build(df)["T"]["12:00"]["res"][("S0.1/T0.2", "L")][20]
        self.assertAlmostEqual(r, -0.1 * atr)

    def test_no_edge_in_random_data_means_nothing_survives_validation_often(self):
        res = search(self.data, 0.58, min_train=10, min_val=5)
        self.assertGreater(len(res), 100)
        self.assertTrue(set(["t_train", "t_val", "t_test"]) <= set(res.columns))
        nl = null_runs(self.data, 0.58, 2)
        self.assertEqual(len(nl), 2)

    def test_stat_handles_small_samples(self):
        n, m, t = stat(np.arange(3.0), np.array([True, True, True]), 0.5)
        self.assertEqual(n, 3)
        self.assertTrue(np.isnan(m))


if __name__ == "__main__":
    unittest.main()
