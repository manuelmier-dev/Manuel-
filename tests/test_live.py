import unittest

import pandas as pd

from bot.backtest import run_backtest
from bot.days import build_days
from bot.live import bars_from_api, describe, simulate
from test_tsbars import P, premarket, scenario, summary

NY = "America/New_York"


class TestLive(unittest.TestCase):
    def setUp(self):
        rth, _ = scenario([5030, 5015, 5004, 5000])
        self.bars = pd.concat([premarket("2024-01-03"), rth])
        days, _ = build_days(summary(), self.bars)
        self.trades, _ = run_backtest(self.bars, days, P)
        self.assertEqual(len(self.trades), 1)

    def test_replay_of_the_full_day_reproduces_the_backtest(self):
        now = pd.Timestamp("2024-01-03 16:00", tz=NY)
        res = simulate(summary(), self.bars, now, P)
        self.assertEqual(res["estado"], "OPERA")
        self.assertEqual(len(res["operaciones"]), 1)
        o, t = res["operaciones"][0], self.trades.iloc[0]
        self.assertEqual((o["lado"], o["estado"]), (t["side"], "CERRADA"))
        self.assertAlmostEqual(o["entrada"], t["entry"])
        self.assertAlmostEqual(o["stop"], t["stop"])

    def test_decides_to_enter_exactly_when_the_signal_bar_closes(self):
        entry_start = self.trades.iloc[0]["entry_time"]                 # inicio de la barra de entrada = cierre de la barra de señal
        res = simulate(summary(), self.bars, entry_start, P)
        self.assertEqual(res["operaciones"][0]["estado"], "ENTRAR_AHORA")
        text = "\n".join(describe(res, entry_start))
        self.assertIn("ENVIARÍA", text)
        self.assertIn("SELL 1 ES a mercado", text)

    def test_no_signal_before_and_open_position_after(self):
        before = self.trades.iloc[0]["entry_time"] - pd.Timedelta(minutes=10)
        self.assertEqual(simulate(summary(), self.bars, before, P)["operaciones"], [])
        after = self.trades.iloc[0]["entry_time"] + pd.Timedelta(minutes=5)
        st = simulate(summary(), self.bars, after, P)["operaciones"][0]["estado"]
        self.assertIn(st, ("ABIERTA", "CERRADA"))

    def test_negative_gamma_day_does_not_trade(self):
        s = summary()
        s["gex_bn"] = -2.0
        res = simulate(s, self.bars, pd.Timestamp("2024-01-03 12:00", tz=NY), P)
        self.assertEqual((res["estado"], res["motivo"]), ("NO_OPERA", "gamma_negativo_tendencia"))

    def test_bars_from_api_converts_close_stamp_to_ny_start(self):
        api = pd.DataFrame({"open": [1.0], "high": [1.0], "low": [1.0], "close": [1.0], "volume": [1.0]},
                           index=pd.DatetimeIndex([pd.Timestamp("2026-10-15 13:35", tz="UTC")]))
        self.assertEqual(bars_from_api(api).index[0], pd.Timestamp("2026-10-15 09:30", tz=NY))


if __name__ == "__main__":
    unittest.main()
