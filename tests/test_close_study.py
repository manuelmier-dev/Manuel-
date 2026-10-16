import unittest

import numpy as np
import pandas as pd

from bot.close_study import evaluate, normalize, raw_day_features

NY = "America/New_York"


def day_bars(day, big_after, vol_before=1000.0, noise=0.0):
    idx = pd.date_range(f"{day} 14:00", f"{day} 15:55", freq="5min", tz=NY)
    px = 5000.0 + np.cumsum(np.full(len(idx), 0.5))
    df = pd.DataFrame({"open": px, "high": px + 1, "low": px - 1, "close": px + 0.5, "volume": vol_before}, index=idx)
    late = df.index >= pd.Timestamp(f"{day} 15:45", tz=NY)
    df.loc[late, "close"] = df.loc[late, "open"] + big_after
    df.loc[late, "high"] = df.loc[late, "close"] + 1
    return df


class TestCloseStudy(unittest.TestCase):
    def test_features_use_only_past_for_signals(self):
        b = day_bars("2024-03-04", 3.0)
        f = raw_day_features(b, "2024-03-04", 5000.0, 10.0, 5010.0, 4980.0, 20.0, -1.0)
        self.assertAlmostEqual(f["Y_mov"], 3.0 + 0.0, delta=3.1)
        self.assertGreater(f["Y_rng"], 0)
        self.assertIsNotNone(f["S2_dist"])
        self.assertIsNone(raw_day_features(b.iloc[:5], "2024-03-04", 5000.0, 10.0, 5010.0, 4980.0, 20.0, -1.0))

    def test_detects_a_planted_relation_and_rejects_noise(self):
        rng = np.random.default_rng(3)
        rows = []
        for i, d in enumerate(pd.bdate_range("2023-01-02", periods=300)):
            gex = rng.normal()
            f = raw_day_features(day_bars(d.date(), 0.0), d, 5000.0, 10.0, 5010.0, 4980.0, 20.0, gex)
            f["Y_mov"] = max(0.1, 3 - 2 * gex + rng.normal(0, 0.5))       # GEX negativo => más movimiento
            f["Y_rng"] = f["Y_mov"] + rng.normal(0, 0.3)
            f["S3_rng"], f["S5_vol"], f["S6_imp"] = (rng.uniform(1, 2) for _ in range(3))   # ruido
            rows.append(f)
        res = evaluate(normalize(pd.DataFrame(rows)), n_perm=300).set_index(["señal", "resultado"])
        self.assertEqual(res.loc[("S1_gex", "Z_mov"), "veredicto"], "RELACIÓN")
        self.assertEqual(res.loc[("S3_rng", "Z_mov"), "veredicto"], "SIN RELACIÓN")

    def test_normalization_does_not_peek(self):
        df = pd.DataFrame({"date": pd.bdate_range("2024-01-01", periods=30), "S1_gex": 0.0, "S2_dist": 1.0, "S3_rng": 1.0, "S5_vol": 1.0,
                           "S6_imp": 1.0, "Y_mov": 1.0, "Y_rng": 1.0})
        df.loc[25, "Y_mov"] = 100.0
        n = normalize(df)
        self.assertEqual(n["Z_mov"].iloc[0], 1.0)            # la mediana previa no incluye el valor de hoy
        self.assertEqual(n["Z_mov"].max(), 100.0)


if __name__ == "__main__":
    unittest.main()
