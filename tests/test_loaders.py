import unittest

import numpy as np
import pandas as pd

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


if __name__ == "__main__":
    unittest.main()
