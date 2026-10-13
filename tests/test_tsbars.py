import os
import tempfile
import unittest
from datetime import date

import pandas as pd

from bot.pipeline import backtest_from_summary, report
from bot.tsbars import check_bars, load_tradestation_bars_csv
from test_bot import P, scenario

NY = "America/New_York"


def el_date(d):
    return (d.year - 1900) * 10000 + d.month * 100 + d.day


def ts_csv(days=("2026-10-12", "2026-10-13"), shift_hours=0):
    """CSV como lo escribe ExportBarras5min: fecha EasyLanguage y hora de CIERRE de cada barra. Datos inventados."""
    rows = []
    for dstr in days:
        d = pd.Timestamp(dstr)
        for s in pd.date_range(f"{dstr} 09:00", f"{dstr} 15:55", freq="5min"):
            c = s + pd.Timedelta(minutes=5) + pd.Timedelta(hours=shift_hours)
            vol = 5000 if s.strftime("%H:%M") == "09:30" else 100
            rows.append(f"{el_date(d)},{c.hour * 100 + c.minute},7800.00,7801.00,7799.00,7800.50,{vol}")
    path = os.path.join(tempfile.mkdtemp(), "es.csv")
    with open(path, "w") as f:
        f.write("fecha_el,hora_cierre,open,high,low,close,volume\n" + "\n".join(rows) + "\n")
    return path


def premarket(date_str):
    idx = pd.date_range(f"{date_str} 09:00", f"{date_str} 09:25", freq="5min", tz=NY)
    return pd.DataFrame({"open": 5000.0, "high": 5000.0, "low": 5000.0, "close": 5000.0, "volume": 100.0}, index=idx)


def summary(spot=5000.0):
    return pd.DataFrame([{"date": pd.Timestamp("2024-01-03"), "spot": spot, "gex_bn": 1.0, "gex_ratio": 0.3,
                          "em_tradestation": 40.0, "em_straddle": 45.0, "call_wall_oi": 5040.0, "put_wall_oi": 4960.0}])


class TestTradeStationBars(unittest.TestCase):
    def test_close_time_becomes_start_time_in_ny(self):
        b = load_tradestation_bars_csv(ts_csv())
        self.assertEqual(str(b.index.tz), NY)
        self.assertEqual(b.index[0], pd.Timestamp("2026-10-12 09:00", tz=NY))
        self.assertEqual(b.loc[pd.Timestamp("2026-10-13 09:30", tz=NY), "volume"], 5000)

    def test_wrong_timezone_is_detected(self):
        with self.assertRaises(ValueError):
            load_tradestation_bars_csv(ts_csv(shift_hours=1))

    def test_el_date_conversion(self):
        self.assertEqual(el_date(date(2026, 10, 13)), 1261013)

    def test_check_bars(self):
        c = check_bars(load_tradestation_bars_csv(ts_csv()))
        self.assertEqual((c["dias"], c["dias_con_sesion_completa"], c["dias_con_premercado_9_a_9_25"]), (2, 2, 2))


class TestPipeline(unittest.TestCase):
    def test_end_to_end_short_hits_target(self):
        rth, _ = scenario([5030, 5015, 5004, 5000])
        trades, skipped, days, skipped_days = backtest_from_summary(summary(), pd.concat([premarket("2024-01-03"), rth]), P)
        self.assertEqual(skipped_days, [])
        self.assertEqual(len(trades), 1)
        self.assertEqual(trades.iloc[0]["reason"], "target")
        rep = report(trades, skipped, days)
        self.assertEqual(rep["general"]["operaciones"], 1)
        self.assertIn("entrada_1", rep)

    def test_absurd_basis_skips_day(self):
        rth, _ = scenario([5030, 5015, 5004, 5000])
        trades, _, _, skipped_days = backtest_from_summary(summary(spot=4500.0), pd.concat([premarket("2024-01-03"), rth]), P)
        self.assertTrue(trades.empty)
        self.assertEqual(len(skipped_days), 1)
        self.assertIn("fuera de lo normal", skipped_days[0])


if __name__ == "__main__":
    unittest.main()
