import unittest

import numpy as np
import pandas as pd

from bot.flow import (SLICES, bs_price, bucket_features, delta_gamma, implied_vol, normalize_trades, sign_trades, day_flow)

NY = "America/New_York"


class TestFlow(unittest.TestCase):
    def test_implied_vol_roundtrip(self):
        s, k, t = 5000.0, np.array([4950.0, 5000.0, 5050.0]), np.full(3, 3 / (365 * 24))
        for call in (True, False):
            p = bs_price(s, k, t, 0.18, call)
            iv = implied_vol(p, s, k, t, call)
            self.assertTrue(np.allclose(iv, 0.18, atol=1e-3), iv)

    def test_delta_gamma_atm(self):
        d, g = delta_gamma(5000.0, 5000.0, 1 / 365, 0.2, True)
        self.assertAlmostEqual(float(d), 0.5, delta=0.02)
        self.assertGreater(float(g), 0)
        dp, _ = delta_gamma(5000.0, 5000.0, 1 / 365, 0.2, False)
        self.assertAlmostEqual(float(dp), float(d) - 1, places=6)

    def test_sign(self):
        tr = pd.DataFrame({"price": [10.0, 9.0, 9.5, 10.0], "bid": [9.0, 9.0, 9.0, 0.0], "ask": [10.0, 10.0, 10.0, 10.0]})
        self.assertEqual(sign_trades(tr).tolist(), [1, -1, 0, 0])

    def test_customer_buys_calls_means_dealers_short_delta(self):
        ts = pd.Timestamp("2026-10-13 09:31:00", tz=NY)
        price = float(bs_price(5000.0, 5000.0, 6.5 / (365 * 24), 0.15, True))
        tr = pd.DataFrame({"ts": [ts], "strike": [5000.0], "right": ["C"], "size": [10], "price": [price],
                           "bid": [price - 0.5], "ask": [price]})
        f = bucket_features(tr, lambda t: 5000.0)
        self.assertEqual(f.loc[0, "cust_buy_c"], 10)
        self.assertLess(f.loc[0, "dealer_delta"], 0)           # dealers vendieron calls -> short delta
        self.assertLess(f.loc[0, "dealer_gamma"], 0)
        self.assertEqual(f.loc[0, "bucket"], "09:30")

    def test_normalize_and_day_flow_with_fake_fetch(self):
        raw = "trade_timestamp,strike,right,size,price,bid,ask\n2026-10-13T09:31:00.5,5000,CALL,3,5.0,4.5,5.0\n"
        df = pd.read_csv(pd.io.common.StringIO(raw))
        self.assertEqual(len(normalize_trades(df, "2026-10-13")), 1)
        idx = pd.date_range("2026-10-13 09:00", "2026-10-13 10:30", freq="5min", tz=NY)
        es = pd.DataFrame({"close": 5000.0}, index=idx)
        calls = []
        def fetch(url):
            calls.append(url)
            return 200, raw
        out = day_flow("2026-10-13", 4990.0, es, fetch)
        self.assertEqual(len(calls), len(SLICES))
        self.assertEqual(out["cust_buy_c"].sum(), 3 * len(SLICES))


if __name__ == "__main__":
    unittest.main()
