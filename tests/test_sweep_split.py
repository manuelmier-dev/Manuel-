import unittest

import numpy as np
import pandas as pd

from bot.sweep_split import period_metrics, summarize_split


class TestSweepSplit(unittest.TestCase):
    def test_small_periods_are_not_scored(self):
        self.assertTrue(np.isnan(period_metrics(pd.DataFrame({"usd": [1.0] * 5}))["usd_op"]))
        m = period_metrics(pd.DataFrame({"usd": [100.0, -50.0] * 30}))
        self.assertEqual((m["n"], round(m["usd_op"], 1), round(m["pf"], 2)), (60, 25.0, 2.0))

    def test_summary_shows_no_persistence_when_train_and_test_are_unrelated(self):
        rng = np.random.default_rng(0)
        res = pd.DataFrame({"usd_op_train": rng.normal(0, 30, 40), "usd_op_test": rng.normal(0, 30, 40)})
        text = " ".join(summarize_split(res))
        self.assertIn("Correlación", text)
        res2 = pd.DataFrame({"usd_op_train": np.arange(40.0), "usd_op_test": np.arange(40.0) * 2})
        self.assertIn("1.00", " ".join(summarize_split(res2)))


if __name__ == "__main__":
    unittest.main()
