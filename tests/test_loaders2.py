import os
import tempfile
import unittest

import numpy as np
import pandas as pd

from bot.gex import _bs_call, _ncdf, gamma_from_quotes
from bot.loaders import _layout, load_chain_file, parse_chain_frame, read_raw, snapshot_et_from_filename

S, SIG = 5000.0, 0.004   # SIG = volatilidad * raíz(tiempo)
STRIKES = np.arange(4960, 5041, 5.0)


def prices():
    call = _bs_call(S, STRIKES, SIG)
    put = call - S + STRIKES
    d1 = (np.log(S / STRIKES) + 0.5 * SIG**2) / SIG
    return call, put, _ncdf(d1)


def no_gamma_sheet(garbage=True):
    """Hoja como la de agosto: sin símbolo ni gamma. Datos inventados."""
    call, put, delta = prices()
    rows = [["C A L L S"] + [None] * 10,
            ["Pos", "Open Int", "Delta", "Bid", "Ask", "Strike", "Bid", "Ask", "Delta", "Open Int", "Pos"],
            ["17 Aug 26\t(0d)\t Weekly  (Custom=(±19.69)), 17.53%, (Custom=)"] + [None] * 10]
    for k, c, p, d in zip(STRIKES, call, put, delta):
        rows.append([None, "1,000", round(float(d), 2), round(float(c) - 0.05, 2), round(float(c) + 0.05, 2), int(k),
                     round(float(p) - 0.05, 2), round(float(p) + 0.05, 2), round(float(d) - 1, 2), "2,000", None])
    if garbage:
        rows.append([None, 0, 0.54, 554.2, 556.9, 5105, 435.3, 437.7, -0.47, 0, None])
        rows.append([None, 0, 0.54, 551.2, 553.9, 5110, 437.0, 439.4, -0.47, 0, None])
    return pd.DataFrame(rows)


class TestGammaFromQuotes(unittest.TestCase):
    def test_recovers_known_gamma(self):
        call, put, _ = prices()
        g = gamma_from_quotes(STRIKES, call, put, S)
        d1 = (np.log(S / STRIKES) + 0.5 * SIG**2) / SIG
        true = np.exp(-0.5 * d1**2) / np.sqrt(2 * np.pi) / (S * SIG)
        near = np.abs(STRIKES - S) <= 30
        self.assertTrue(np.allclose(g.values[near], true[near], rtol=0.02))

    def test_no_price_gives_nan(self):
        g = gamma_from_quotes([5000.0, 5010.0], [np.nan, 3.0], [np.nan, 12.0], 5000.0)
        self.assertTrue(np.isnan(g.iloc[0]))


class TestNoGammaLayout(unittest.TestCase):
    def test_layout_detected(self):
        self.assertEqual(_layout(no_gamma_sheet()), "sin_gamma")

    def test_parse_estimates_gamma_and_drops_garbage_rows(self):
        out = parse_chain_frame(no_gamma_sheet(), pd.Timestamp(2026, 8, 17))
        self.assertEqual(out["gamma_fuente"], "estimada")
        self.assertEqual(out["n_strikes"], len(STRIKES))          # las 2 filas basura no cuentan
        self.assertAlmostEqual(out["spot"], S, delta=2)
        self.assertEqual(out["em_tradestation"], 19.69)
        self.assertLess(out["gex_bn"], 0)                          # más OI de puts que de calls

    def test_file_with_two_expirations_is_rejected(self):
        sheet = no_gamma_sheet(garbage=False)
        doubled = pd.concat([sheet, sheet.iloc[3:]], ignore_index=True)      # mismos strikes dos veces = dos vencimientos
        with self.assertRaises(ValueError) as cm:
            parse_chain_frame(doubled, pd.Timestamp(2026, 8, 17))
        self.assertIn("más de un vencimiento", str(cm.exception))

    def test_wrong_expiry_date_is_rejected(self):
        with self.assertRaises(ValueError):
            parse_chain_frame(no_gamma_sheet(), pd.Timestamp(2026, 8, 18))


class TestSnapshotAndCsv(unittest.TestCase):
    def test_name_time_is_merida_converted_to_ny(self):
        t = snapshot_et_from_filename("SPX 0DTE 17-08-2026 7.20am.xls", pd.Timestamp(2026, 8, 17))
        self.assertEqual(t.strftime("%H:%M"), "09:20")             # verano: Mérida = NY - 2 h
        w = snapshot_et_from_filename("SPX 0DTE 15-12-2026 7.20am.xls", pd.Timestamp(2026, 12, 15))
        self.assertEqual(w.strftime("%H:%M"), "08:20")             # invierno: Mérida = NY - 1 h
        self.assertIsNone(snapshot_et_from_filename("sin_hora.xls", pd.Timestamp(2026, 8, 17)))

    def test_file_exported_after_open_is_rejected(self):
        d = tempfile.mkdtemp()
        path = os.path.join(d, "SPX 0DTE 17-08-2026 9.07am.csv")   # 9:07 Mérida = 11:07 NY
        with open(path, "w") as f:
            f.write("x")
        with self.assertRaises(ValueError) as cm:
            load_chain_file(path)
        self.assertIn("después de la apertura", str(cm.exception))

    def test_csv_with_cp1252_plus_minus_sign(self):
        d = tempfile.mkdtemp()
        path = os.path.join(d, "SPX 0DTE 14-09-2026 7.20am.csv")
        call, put, _ = prices()
        lines = ["C A L L S" + "," * 18,
                 "Pos,Symbol,Gamma,Imp Volatility,Volume,Open Int,Delta,Bid,Ask,Strike,Bid,Ask,Delta,Open Int,Imp Volatility,Volume,Gamma,Symbol,Pos",
                 '"   14 Sep 26\t(0d)\t Weekly  (Custom=(±24.94)), 22.50%, (Custom=)"' + "," * 18]
        for k, c, p in zip(STRIKES, call, put):
            lines.append(f',SPXW 260914C{int(k)},0.008,20 %,0,"1,000",0.5,{c - .05:.2f},{c + .05:.2f},{int(k)},{p - .05:.2f},{p + .05:.2f},-0.5,"2,000",20 %,0,0.008,SPXW 260914P{int(k)},')
        with open(path, "w", encoding="cp1252", newline="") as f:
            f.write("\n".join(lines) + "\n")
        out = load_chain_file(path)
        self.assertEqual(out["em_tradestation"], 24.94)
        self.assertEqual(out["gamma_fuente"], "archivo")
        self.assertEqual(out["snapshot_et"], "09:20")


if __name__ == "__main__":
    unittest.main()
