import unittest
from datetime import time

import numpy as np
import pandas as pd

from bot.journal import build_journal, first_hour_stats, regime_report

NY = "America/New_York"


def day_bars(date="2026-10-13", high_at="09:45", low_at="14:00"):
    idx = pd.date_range(f"{date} 09:30", f"{date} 15:55", freq="5min", tz=NY)
    px = pd.Series(5000.0, index=idx)
    px[pd.Timestamp(f"{date} {high_at}", tz=NY)] = 5030.0
    px[pd.Timestamp(f"{date} {low_at}", tz=NY)] = 4980.0
    px.iloc[-1] = 5010.0
    return pd.DataFrame({"open": px, "high": px, "low": px, "close": px, "volume": 100.0})


def summary_row(date="2026-10-13", gex=5.0, em=25.0):
    return {"date": pd.Timestamp(date), "spot": 5000.0, "gex_bn": gex, "gex_ratio": 0.3,
            "em_tradestation": em, "em_straddle": 30.0, "call_wall_oi": 5025.0, "put_wall_oi": 4975.0}


class TestJournal(unittest.TestCase):
    def test_post_close_values(self):
        j = build_journal(pd.DataFrame([summary_row()]), day_bars())
        r = j.iloc[0]
        self.assertEqual((r["es_high"], r["es_low"], r["es_close"]), (5030.0, 4980.0, 5010.0))
        self.assertEqual(r["range_pts"], 50.0)
        self.assertAlmostEqual(r["range_em"], 2.0)
        self.assertEqual(r["high_time"], time(9, 45))
        self.assertTrue(r["high_in_window"])
        self.assertFalse(r["low_in_window"])
        self.assertAlmostEqual(r["close_pos"], 0.6)
        self.assertEqual(r["regime"], "reversion")
        self.assertTrue(r["bot_opera"])

    def test_negative_gamma_is_trend_and_not_traded(self):
        j = build_journal(pd.DataFrame([summary_row(gex=-3.0)]), day_bars())
        self.assertEqual(j.iloc[0]["regime"], "tendencia")
        self.assertFalse(j.iloc[0]["bot_opera"])
        self.assertEqual(j.iloc[0]["motivo_no_opera"], "gamma_negativo_tendencia")

    def test_low_em_not_traded(self):
        j = build_journal(pd.DataFrame([summary_row(em=18.0)]), None)
        self.assertEqual(j.iloc[0]["motivo_no_opera"], "movimiento_esperado_bajo")

    def test_without_bars_post_close_is_empty(self):
        j = build_journal(pd.DataFrame([summary_row()]), None)
        self.assertTrue(np.isnan(j.iloc[0]["range_pts"]))
        self.assertEqual(first_hour_stats(j), {"dias_con_barras": 0})

    def test_incomplete_session_is_not_used(self):
        short = day_bars().between_time("09:30", "11:00")
        j = build_journal(pd.DataFrame([summary_row()]), short)
        self.assertTrue(np.isnan(j.iloc[0]["range_pts"]))

    def test_other_day_bars_are_not_mixed_in(self):
        j = build_journal(pd.DataFrame([summary_row("2026-10-14")]), day_bars("2026-10-13"))
        self.assertTrue(np.isnan(j.iloc[0]["range_pts"]))

    def test_stats_and_regime_report(self):
        bars = pd.concat([day_bars("2026-10-12", "09:45", "14:00"), day_bars("2026-10-13", "13:00", "14:00")])
        j = build_journal(pd.DataFrame([summary_row("2026-10-12"), summary_row("2026-10-13", gex=-2.0)]), bars)
        s = first_hour_stats(j)
        self.assertEqual(s["dias_con_barras"], 2)
        self.assertEqual(s["alguno_de_los_dos_%"], 50.0)
        rep = regime_report(j)
        self.assertEqual(set(rep.index), {"reversion", "tendencia"})


if __name__ == "__main__":
    unittest.main()
