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


class TestRejection(unittest.TestCase):
    @staticmethod
    def spike_day(high, close):
        """Día plano en 5000 con una sola barra (la 12) que sube a 'high' y cierra en 'close'. Wall de calls en 5040, EM 40."""
        b, d = scenario([5000])
        for col in ("open", "high", "low", "close"):
            b[col] = 5000.0
        i = 12
        b.iloc[i, b.columns.get_loc("high")] = high
        b.iloc[i, b.columns.get_loc("close")] = close
        for col in ("open", "high", "low", "close"):                 # y el precio se queda donde cerró la barra de la señal
            b.iloc[i + 1:, b.columns.get_loc(col)] = close
        return b, d

    def test_breakout_bar_is_blocked_only_when_rejection_is_required(self):
        from dataclasses import replace
        b, d = self.spike_day(high=5050.0, close=5050.0)           # cierra ARRIBA del wall: se rompió
        base = replace(P, confirmations_required=0)
        free, _ = run_backtest(b, d, replace(base, require_rejection=False))
        strict, _ = run_backtest(b, d, replace(base, require_rejection=True))
        self.assertGreaterEqual(len(free), 1)
        self.assertEqual(free.iloc[0]["side"], "short")
        self.assertEqual(len(strict), 0)

    def test_rejected_touch_is_allowed(self):
        from dataclasses import replace
        b, d = self.spike_day(high=5045.0, close=5030.0)           # tocó el wall pero cerró debajo: rebote (y luego se queda en 5030)
        strict, _ = run_backtest(b, d, replace(P, confirmations_required=0, require_rejection=True))
        self.assertGreaterEqual(len(strict), 1)
        self.assertEqual(strict.iloc[0]["side"], "short")


class TestSecondEntryModes(unittest.TestCase):
    def test_modes_after_a_stop(self):
        from dataclasses import replace
        b, d = scenario([5050, 5060, 5070, 5080])
        same, _ = run_backtest(b, d, P)
        none, _ = run_backtest(b, d, replace(P, second_entry="ninguna"))
        rev, _ = run_backtest(b, d, replace(P, second_entry="reversa"))
        self.assertEqual(len(none), 1)
        self.assertEqual(none.iloc[0]["reason"], "stop")
        self.assertEqual(rev.iloc[0]["tipo"], "normal")
        if len(rev) == 2:
            self.assertEqual(rev.iloc[1]["tipo"], "reversa")
            self.assertEqual(rev.iloc[1]["side"], "long")           # contrario al corto que se rompió
        self.assertIn("tipo", same.columns)


if __name__ == "__main__":
    unittest.main()
