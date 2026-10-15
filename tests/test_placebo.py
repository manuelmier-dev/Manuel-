import unittest

import numpy as np
import pandas as pd

from bot.placebo import metrics, shuffle_walls


class TestPlacebo(unittest.TestCase):
    def test_shuffle_keeps_relative_offsets_and_pairs(self):
        n = 50
        days = pd.DataFrame({"em_pts": np.full(n, 25.0), "center_spx": 5000 + np.arange(n) * 3.0,
                             "call_wall": 5000 + np.arange(n) * 3.0 + np.arange(n) * 0.5, "put_wall": 5000 + np.arange(n) * 3.0 - np.arange(n) * 0.7})
        out = shuffle_walls(days, np.random.default_rng(0))
        oc_in = np.sort((days["call_wall"] - days["center_spx"]) / days["em_pts"])
        oc_out = np.sort((out["call_wall"] - out["center_spx"]) / out["em_pts"])
        self.assertTrue(np.allclose(oc_in, oc_out))                                  # mismas posiciones relativas, repartidas distinto
        self.assertFalse(np.allclose(out["call_wall"], days["call_wall"]))
        pair_ok = np.allclose((out["call_wall"] - out["center_spx"]) / 25 * 0.7 / 0.5 * -1, (out["put_wall"] - out["center_spx"]) / 25, atol=1e-9)
        self.assertTrue(pair_ok)                                                       # el par call/put de un día viaja junto

    def test_metrics_handles_empty_and_normal(self):
        self.assertEqual(metrics(pd.DataFrame(columns=["usd"]))["operaciones"], 0)
        m = metrics(pd.DataFrame({"usd": [100.0, -50.0, -50.0, 200.0]}))
        self.assertEqual((m["operaciones"], m["total_usd"], m["aciertos_%"]), (4, 200.0, 50.0))
        self.assertAlmostEqual(m["factor_ganancia"], 3.0)


if __name__ == "__main__":
    unittest.main()
