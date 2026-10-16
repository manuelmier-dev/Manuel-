import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from bot.close_download import day_quotes, normalize_snapshot
from bot.close_pnl import build_daily, pick_contract, run_rules, settle_spot, spot_at, trade_pnl, wide
from bot.flow import bs_price

STRIKES = np.arange(4900.0, 5101.0, 5.0)


def chain(t, spot, minutes_left, vol=0.6):
    T = max(minutes_left, 0.05) / (365 * 24 * 60)
    rows = []
    for right, call in (("C", True), ("P", False)):
        px = np.asarray(bs_price(spot, STRIKES, T, vol, call), float)
        for k, p in zip(STRIKES, px):
            rows.append({"t": t, "strike": k, "right": right, "bid": max(round(p - 0.05, 2), 0), "ask": round(p + 0.05, 2), "ask_size": 20})
    return rows


def day(spot_entry=5000.0, spot_end=5020.0):
    rows = chain("15:30:00", spot_entry, 30) + chain("15:45:00", spot_entry, 15)
    rows += chain("15:50:00", spot_entry + (spot_end - spot_entry) * 0.6, 10) + chain("15:55:00", spot_entry + (spot_end - spot_entry) * 0.9, 5)
    rows += chain("15:59:59", spot_end, 0.02, vol=0.05)
    return pd.DataFrame(rows)


class TestClosePnl(unittest.TestCase):
    def test_spot_estimates(self):
        q = day()
        self.assertAlmostEqual(spot_at(wide(q, "15:45:00")), 5000.0, delta=3)
        self.assertAlmostEqual(settle_spot(wide(q, "15:59:59")), 5020.0, delta=1.0)

    def test_contract_respects_filters(self):
        z = wide(day(), "15:45:00")
        k = pick_contract(z, 5000.0, +1, 0.002)
        self.assertIsNotNone(k)
        self.assertGreater(k["strike"], 5000.0)
        self.assertTrue(0.30 <= k["ask"] <= 3.0)
        z.loc[:, "ask_size_c"] = 1                       # sin tamaño suficiente: no se opera
        self.assertIsNone(pick_contract(z, 5000.0, +1, 0.002))

    def test_pnl_signs_and_costs(self):
        q = day(5000.0, 5030.0)
        win = trade_pnl(q, "15:45", +1, 0.002, "A")
        lose = trade_pnl(q, "15:45", -1, 0.002, "A")
        self.assertGreater(win["pnl"], 0)
        self.assertAlmostEqual(lose["pnl"], -lose["cost"] - 0.65, places=6)        # put vence sin valor: se pierde prima + comisiones
        self.assertGreaterEqual(win["cost"], (win["premium"] + 0.05) * 100 + 0.65 - 1e-9)

    def test_exit_b_uses_bid_not_mid(self):
        b = trade_pnl(day(5000.0, 5030.0), "15:45", +1, 0.002, "B")
        self.assertIsNotNone(b)
        self.assertGreater(b["cost"], 0)

    def test_download_with_fake_theta(self):
        calls = []
        def fetch(url):
            calls.append(url)
            t = [x for x in ("15:30", "15:45", "15:50", "15:55", "15:59") if x in url][0]
            q = day()
            q = q[q["t"].str.startswith(t)]
            csv = q.rename(columns={"right": "right"})[["strike", "right", "bid", "ask", "ask_size"]].replace({"C": "CALL", "P": "PUT"}).to_csv(index=False)
            return 200, csv
        out = day_quotes("2024-03-04", fetch)
        self.assertEqual(out["t"].nunique(), 5)
        self.assertEqual(len(calls), 5)

    def test_build_daily_end_to_end(self):
        tmp = Path(tempfile.mkdtemp())
        dates = pd.bdate_range("2023-01-02", periods=70)
        bars = []
        for d in dates:
            idx = pd.date_range(f"{d.date()} 15:00", f"{d.date()} 15:55", freq="5min", tz="America/New_York")
            px = 5000.0 + np.arange(len(idx)) * 0.8
            bars.append(pd.DataFrame({"open": px, "high": px + 1, "low": px - 1, "close": px + 0.5, "volume": 100.0}, index=idx))
            day().to_csv(tmp / f"{d.date()}.csv", index=False)
        feats = pd.DataFrame({"gex_bn": -1.0}, index=dates)
        daily = build_daily(tmp, feats, pd.concat(bars))
        self.assertGreater(len(daily), 0)
        self.assertEqual(set(daily["entry"]), {"15:30", "15:45"})
        self.assertTrue(daily["pnl_regla"].notna().any())

    def test_rules_need_evidence(self):
        rng = np.random.default_rng(2)
        n = 250
        g = pd.DataFrame({"date": pd.bdate_range("2023-01-02", periods=n), "entry": "15:45", "dist": 0.002, "exit": "A",
                          "pnl_regla": rng.choice([-45.0, 300.0], n, p=[0.88, 0.12]), "pnl_opuesto": rng.choice([-45.0, 300.0], n, p=[0.88, 0.12])})
        res = run_rules(g, n_placebo=300)
        self.assertEqual(res.loc[0, "veredicto"], "SIN VENTAJA")                         # ruido con cola: no debe salir candidata
        g["pnl_regla"] = rng.choice([-45.0, 400.0], n, p=[0.6, 0.4])                    # ventaja grande y repartida
        self.assertEqual(run_rules(g, n_placebo=300).loc[0, "veredicto"], "CANDIDATA")


if __name__ == "__main__":
    unittest.main()
