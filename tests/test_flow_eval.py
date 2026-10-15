import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from bot.flow_eval import day_features, directions, evaluate

NY = "America/New_York"


class TestFlowEval(unittest.TestCase):
    def test_signal_with_edge_is_detected_and_noise_is_not(self):
        rng = np.random.default_rng(1)
        dates = pd.bdate_range("2024-01-02", periods=90)
        tmp = Path(tempfile.mkdtemp())
        rows, truth = [], {}
        for d in dates:
            p = rng.normal()
            truth[d] = p
            pd.DataFrame({"vol": [100], "vol_clasif": [80], "dealer_delta": [-p * 1000], "dealer_gamma": [-1.0]}).to_csv(tmp / f"{d.date()}.csv", index=False)
            for hhmm, off in (("10:30", 0.0), ("12:30", np.sign(p) * 3.0), ("15:55", np.sign(p) * 6.0 + rng.normal())):
                rows.append((pd.Timestamp(f"{d.date()} {hhmm}", tz=NY), 5000 + off))
        es = pd.DataFrame({"open": [r[1] for r in rows]}, index=[r[0] for r in rows])
        feat = day_features(tmp)
        self.assertEqual(len(feat), 90)
        res = evaluate(feat, es, n_placebo=200).set_index(["regla", "salida"])
        self.assertEqual(res.loc[("F1", "15:55"), "veredicto"], "CANDIDATA")
        self.assertLess(res.loc[("F2", "15:55"), "usd_prom"], 0)
        self.assertEqual(res.loc[("F2", "15:55"), "veredicto"], "SIN VENTAJA")

    def test_f3_uses_only_past(self):
        feat = pd.DataFrame({"P": [1.0, 5.0, 0.5], "G": [-1, -1, 1]}, index=pd.bdate_range("2024-01-02", periods=3))
        d = directions(feat)
        self.assertEqual(d["F3"].tolist(), [0, 1, 0])
        self.assertEqual(d["F4"].tolist(), [1, 1, 0])


if __name__ == "__main__":
    unittest.main()
