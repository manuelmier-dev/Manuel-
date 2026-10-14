import unittest

import numpy as np
import pandas as pd

from datetime import time

from bot.days import build_days
from bot.indicators import add_indicators
from bot.config import Params
from bot.loaders import date_from_filename, parse_chain_frame


def fake_sheet(trade="261013", strikes=range(7790, 7831, 5), spot=7808.0, em_header="22.83"):
    """Hoja con la misma forma que la exportación de TradeStation (datos inventados)."""
    rows = [["C A L L S"] + [None] * 18,
            ["Pos", "Symbol", "Gamma", "Imp Volatility", "Volume", "Open Int", "Delta", "Bid", "Ask", "Strike",
             "Bid", "Ask", "Delta", "Open Int", "Imp Volatility", "Volume", "Gamma", "Symbol", "Pos"],
            [f"13 Oct 26\t(0d)\t Weekly  (Custom=(±{em_header})), 15.66%, (Custom=)"] + [None] * 18]
    for k in strikes:
        call = max(spot - k, 0) + 12 - abs(spot - k) * 0.2
        put = max(k - spot, 0) + 12 - abs(spot - k) * 0.2
        rows.append([None, f"SPXW {trade}C{k}", 0.010, "15.00 %", 0, "1,000", 0.5, call - 0.1, call + 0.1, k,
                     put - 0.1, put + 0.1, -0.5, "2,000", "15.00 %", 0, 0.010, f"SPXW {trade}P{k}", None])
    return pd.DataFrame(rows)


class TestLoaders(unittest.TestCase):
    def test_filename_date(self):
        self.assertEqual(date_from_filename("/x/SPX ODTE 13-10-2026 7.20am.xls"), pd.Timestamp(2026, 10, 13))
        with self.assertRaises(ValueError):
            date_from_filename("sin_fecha.xls")

    def test_parse_summary(self):
        out = parse_chain_frame(fake_sheet(), pd.Timestamp(2026, 10, 13))
        self.assertAlmostEqual(out["spot"], 7808.0, delta=1.0)
        self.assertEqual(out["em_tradestation"], 22.83)
        self.assertEqual(out["n_strikes"], 9)
        # calls 1,000 OI y puts 2,000 OI con la misma gamma -> las puts dominan: GEX negativo
        self.assertLess(out["gex_bn"], 0)
        self.assertEqual(out["put_wall_oi"], 7790.0)  # empate: toma el primero

    def test_rejects_file_without_0dte(self):
        with self.assertRaises(ValueError):
            parse_chain_frame(fake_sheet(trade="261014"), pd.Timestamp(2026, 10, 13))

    def test_missing_header_gives_nan(self):
        sheet = fake_sheet()
        sheet.iloc[2, 0] = "sin encabezado"
        out = parse_chain_frame(sheet, pd.Timestamp(2026, 10, 13))
        self.assertTrue(np.isnan(out["em_tradestation"]))


class TestDays(unittest.TestCase):
    def _bars(self):
        idx = pd.date_range("2024-01-03 08:00", "2024-01-03 10:00", freq="5min", tz="America/New_York")
        close = pd.Series(np.linspace(7800, 7830, len(idx)), index=idx)
        day = pd.DataFrame({"open": close, "high": close, "low": close, "close": close, "volume": 100.0})
        prev = pd.DataFrame({"open": 7800.0, "high": 7800.0, "low": 7800.0, "close": 7800.0, "volume": 100.0},
                            index=[pd.Timestamp("2024-01-02 15:55", tz="America/New_York")])    # cierre del día anterior
        return pd.concat([prev, day])

    def test_build_days_uses_tradestation_em_and_oi_walls(self):
        summ = pd.DataFrame([parse_chain_frame(fake_sheet(), pd.Timestamp(2024, 1, 3).replace(year=2026, month=10, day=13))])
        summ["date"] = pd.Timestamp(2024, 1, 3)
        days, skipped = build_days(summ, self._bars(), wall_mode="oi")
        self.assertEqual(skipped, [])
        row = days.iloc[0]
        self.assertEqual(row["em_pts"], 22.83)
        self.assertEqual(row["call_wall"], summ.iloc[0]["call_wall_oi"])
        # la base sale del CIERRE de ES del día anterior (7800) menos el spot del archivo, no del precio de las 9:15
        self.assertAlmostEqual(row["basis"], 7800.0 - summ.iloc[0]["spot"])

    def test_em_falls_back_to_proxy(self):
        summ = pd.DataFrame([parse_chain_frame(fake_sheet(em_header="x"), pd.Timestamp(2026, 10, 13))])
        summ["date"] = pd.Timestamp(2024, 1, 3)
        days, _ = build_days(summ, self._bars())
        self.assertEqual(days.iloc[0]["em_pts"], summ.iloc[0]["em_proxy"])   # sin EM de TradeStation: 0.70 x straddle

    def test_skips_day_without_premarket_bar(self):
        summ = pd.DataFrame([parse_chain_frame(fake_sheet(), pd.Timestamp(2026, 10, 13))])
        summ["date"] = pd.Timestamp(2024, 1, 3)
        rth_only = self._bars().between_time("09:30", "10:00")      # sin pre-mercado ni cierre previo
        days, skipped = build_days(summ, rth_only)
        self.assertTrue(days.empty)
        self.assertEqual(len(skipped), 1)

    def test_vwap_ignores_premarket(self):
        idx = pd.date_range("2024-01-03 08:00", "2024-01-03 10:00", freq="5min", tz="America/New_York")
        px = np.where(idx.time < time(9, 30), 5000.0, 7800.0)
        b = pd.DataFrame({"open": px, "high": px, "low": px, "close": px, "volume": 100.0}, index=idx)
        out = add_indicators(b, Params())
        self.assertTrue(out.loc[idx.time < time(9, 30), "vwap"].isna().all())
        self.assertEqual(out.loc["2024-01-03 09:30", "vwap"], 7800.0)


if __name__ == "__main__":
    unittest.main()
