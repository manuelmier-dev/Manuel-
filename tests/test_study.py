import tempfile
import unittest
from pathlib import Path

import pandas as pd

from bot.study import day_signals, make_study, summarize_zones
from test_tsbars import P, premarket, scenario, summary


class TestStudy(unittest.TestCase):
    def setUp(self):
        rth, _ = scenario([5030, 5015, 5004, 5000])
        self.bars = pd.concat([premarket("2024-01-03"), rth])

    def test_files_and_one_row_per_day(self):
        out = tempfile.mkdtemp()
        table = make_study(summary(), self.bars, out, P)
        self.assertEqual(len(table), 1)
        self.assertTrue((Path(out) / "estudio_dias.pdf").stat().st_size > 5000)
        self.assertTrue((Path(out) / "png" / "2024-01-03.png").exists())
        self.assertTrue((Path(out) / "estudio_zonas.csv").exists())
        r = table.iloc[0]
        self.assertTrue(r["opera"])
        self.assertEqual(r["operaciones"], 1)
        self.assertGreater(r["resultado_usd"], 0)
        self.assertGreaterEqual(r["toques_de_zona"], 1)

    def test_negative_gamma_day_is_plotted_and_explained(self):
        s = summary()
        s["gex_bn"] = -2.0
        table = make_study(s, self.bars, tempfile.mkdtemp(), P)
        self.assertFalse(table.iloc[0]["opera"])
        self.assertEqual(table.iloc[0]["motivo_no_opera"], "gamma_negativo_tendencia")
        self.assertEqual(table.iloc[0]["regimen"], "tendencia")

    def test_signals_match_what_the_backtest_would_use(self):
        from bot.days import build_days
        from bot.indicators import add_indicators
        days, _ = build_days(summary(), self.bars)
        ind = add_indicators(self.bars, P)
        b = ind[ind.index.date == pd.Timestamp("2024-01-03").date()]
        sigs = day_signals(b, days.iloc[0], P)
        self.assertTrue((sigs["side"] == "short").all())          # solo se toca el call wall
        self.assertTrue(sigs["pasa"].any())

    def test_summary_lines(self):
        table = make_study(summary(), self.bars, tempfile.mkdtemp(), P)
        text = " ".join(summarize_zones(table))
        self.assertIn("Días estudiados: 1", text)


if __name__ == "__main__":
    unittest.main()
