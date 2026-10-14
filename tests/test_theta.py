import unittest

import numpy as np
import pandas as pd

from bot.theta_snapshot import summary_from_theta
from test_loaders2 import S, SIG, STRIKES, prices
from test_loaders import fake_sheet
from bot.loaders import parse_chain_frame


def theta_frames():
    call, put, _ = prices()
    q = pd.concat([pd.DataFrame({"strike": STRIKES, "right": "C", "bid": call - 0.05, "ask": call + 0.05}),
                   pd.DataFrame({"strike": STRIKES, "right": "P", "bid": put - 0.05, "ask": put + 0.05})])
    oi = pd.concat([pd.DataFrame({"strike": STRIKES, "right": "C", "open_interest": 1000}),
                    pd.DataFrame({"strike": STRIKES, "right": "P", "open_interest": 2000})])
    oi.loc[(oi["right"] == "C") & (oi["strike"] == 5020), "open_interest"] = 9000
    oi.loc[(oi["right"] == "P") & (oi["strike"] == 4980), "open_interest"] = 9000
    return q, oi


class TestThetaSnapshot(unittest.TestCase):
    def test_summary_values(self):
        q, oi = theta_frames()
        out = summary_from_theta(pd.Timestamp(2026, 10, 13), q, oi)
        self.assertAlmostEqual(out["spot"], S, delta=2)
        self.assertEqual(out["gamma_fuente"], "estimada")
        self.assertTrue(np.isnan(out["em_tradestation"]))
        self.assertAlmostEqual(out["em_proxy"], out["em_straddle"])           # Theta: en vivo, factor 1.0
        self.assertEqual((out["call_wall_oi"], out["put_wall_oi"]), (5020.0, 4980.0))
        self.assertEqual(out["snapshot_et"], "09:20")

    def test_same_fields_as_the_tradestation_summary(self):
        q, oi = theta_frames()
        theta = summary_from_theta(pd.Timestamp(2026, 10, 13), q, oi)
        ts = parse_chain_frame(fake_sheet(), pd.Timestamp(2026, 10, 13))
        self.assertEqual(set(ts) - {"fuente"}, set(theta) - {"fuente", "_raw"})

    def test_crossed_and_empty_quotes_are_dropped(self):
        q, oi = theta_frames()
        q.loc[(q["right"] == "C") & (q["strike"] == 5000), ["bid", "ask"]] = [5.0, 1.0]     # cruzada
        q.loc[(q["right"] == "P") & (q["strike"] == 5000), ["bid", "ask"]] = [0.0, 0.0]     # vacía
        out = summary_from_theta(pd.Timestamp(2026, 10, 13), q, oi)
        self.assertAlmostEqual(out["spot"], S, delta=2)                                      # el strike dañado no mueve el precio

    def test_no_valid_quotes_raises(self):
        q, oi = theta_frames()
        q["ask"] = 0.0
        with self.assertRaises(ValueError):
            summary_from_theta(pd.Timestamp(2026, 10, 13), q, oi)


if __name__ == "__main__":
    unittest.main()
