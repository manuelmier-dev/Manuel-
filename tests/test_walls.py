import unittest

import numpy as np
import pandas as pd

from bot.backtest import run_backtest
from bot.loaders import parse_chain_frame
from test_bot import P, scenario
from test_loaders import fake_sheet


def sheet_with_oi():
    """Strikes 7700-7900. OI de calls: máximo global en 7900 (lejos) y máximo cercano en 7820. Igual con puts (7700 / 7795)."""
    raw = fake_sheet(strikes=range(7700, 7901, 5), spot=7808.0, em_header="22.83")
    strike = pd.to_numeric(raw[9], errors="coerce")
    for k, c_oi, p_oi in [(7900, 9000, 100), (7820, 4000, 100), (7700, 100, 9000), (7795, 100, 4000)]:
        i = raw.index[strike == k][0]
        raw.loc[i, 5], raw.loc[i, 13] = f"{c_oi:,}", f"{p_oi:,}"
    return raw


class TestWalls(unittest.TestCase):
    def test_walls_global_and_within_one_em(self):
        out = parse_chain_frame(sheet_with_oi(), pd.Timestamp(2026, 10, 13))
        self.assertEqual((out["call_wall_oi"], out["put_wall_oi"]), (7900.0, 7700.0))
        # EM = 22.83: calls entre 7808 y 7830.8; puts entre 7785.2 y 7808
        self.assertEqual((out["call_wall_oi_1em"], out["put_wall_oi_1em"]), (7820.0, 7795.0))

    def test_no_oi_within_window_gives_nan(self):
        raw = fake_sheet(strikes=range(7700, 7901, 5), spot=7808.0)
        raw.loc[3:, 5] = "0"
        out = parse_chain_frame(raw, pd.Timestamp(2026, 10, 13))
        self.assertTrue(np.isnan(out["call_wall_oi_1em"]))

    def test_gex_uses_fixed_window_and_reports_total_separately(self):
        out = parse_chain_frame(sheet_with_oi(), pd.Timestamp(2026, 10, 13))
        self.assertNotEqual(out["gex_bn"], out["gex_bn_total"])      # los strikes lejanos solo entran en el total

    def test_backtest_handles_missing_opposite_wall(self):
        b, d = scenario([5030, 5015, 5004, 5000])
        d["put_wall"] = np.nan
        trades, _ = run_backtest(b, d, P)
        self.assertEqual(len(trades), 1)
        self.assertAlmostEqual(trades.iloc[0]["entry"] - trades.iloc[0]["target"], 36.0)   # 90% de 40, sin wall contrario


class TestIncompleteDay(unittest.TestCase):
    def test_partial_session_is_skipped_not_traded(self):
        b, d = scenario([5030, 5015, 5004, 5000])
        partial = b.between_time("09:30", "11:30")        # el mercado sigue abierto: faltan barras
        trades, skipped = run_backtest(partial, d, P)
        self.assertTrue(trades.empty)
        self.assertEqual(skipped.iloc[0]["reason"], "sesion_incompleta")


if __name__ == "__main__":
    unittest.main()
