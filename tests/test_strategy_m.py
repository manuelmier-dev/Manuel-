import unittest

import numpy as np
import pandas as pd

from bot.strategy_m import add_manuel_indicators, costs, placebo, run, signals, stats

NY = "America/New_York"


def one_day_bars():
    """Un día de 24h (desde las 18:00 del día anterior) con una caída fuerte en pre-mercado y un rebote."""
    idx = pd.date_range("2024-03-04 18:00", "2024-03-05 15:55", freq="5min", tz=NY)
    n = len(idx)
    px = np.full(n, 5000.0)
    k = np.searchsorted(idx, pd.Timestamp("2024-03-05 07:00", tz=NY))
    px[k:k + 20] = 5000 - np.arange(1, 21) * 1.5                 # cae 30 pts
    px[k + 20:k + 26] = px[k + 19] + np.arange(1, 7) * 1.2          # rebota
    px[k + 26:] = px[k + 25]
    close = px
    opens = np.r_[px[0], close[:-1]]
    return pd.DataFrame({"open": opens, "high": np.maximum(opens, close) + 0.2, "low": np.minimum(opens, close) - 0.2,
                         "close": close, "volume": np.where(np.arange(n) % 7 == 0, 500.0, 100.0)}, index=idx)


class TestStrategyM(unittest.TestCase):
    def test_vwap_resets_at_18h_and_indicators_exist(self):
        df = add_manuel_indicators(one_day_bars())
        self.assertTrue(df[["hist", "rsi", "vwap", "vwap_up", "vwap_dn"]].iloc[100:].notna().all().all())
        first = df.loc[pd.Timestamp("2024-03-04 18:00", tz=NY)]
        second_day = df.loc[pd.Timestamp("2024-03-05 18:00", tz=NY)] if pd.Timestamp("2024-03-05 18:00", tz=NY) in df.index else None
        self.assertIsNone(second_day)
        self.assertAlmostEqual(first["vwap"], (first["high"] + first["low"] + first["close"]) / 3)      # la primera barra de la sesión es su propio VWAP

    def test_window_is_0730_to_1030_and_one_per_day(self):
        df = add_manuel_indicators(one_day_bars())
        sig = pd.DataFrame({"entry": False, "exit": False}, index=df.index)
        for hhmm in ("07:00", "07:35", "08:10", "13:40"):                      # una señal antes de las 7:30, y tres después (la última ya de tarde)
            sig.loc[pd.Timestamp(f"2024-03-05 {hhmm}", tz=NY), "entry"] = True
        self.assertEqual(len(run(df, sig, multi=False)), 1)                    # una por día
        late = pd.DataFrame({"entry": False, "exit": False}, index=df.index)
        late.loc[pd.Timestamp("2024-03-05 10:25", tz=NY), "entry"] = True       # entraría a las 10:30: ya fuera de la ventana
        self.assertEqual(len(run(df, late)), 0)
        edge = late.copy()
        edge.loc[pd.Timestamp("2024-03-05 10:25", tz=NY), "entry"] = False
        edge.loc[pd.Timestamp("2024-03-05 10:20", tz=NY), "entry"] = True       # entra a las 10:25: dentro
        self.assertEqual(len(run(df, edge)), 1)
        self.assertEqual(len(run(df, sig, multi=False, win_start="07:30", win_end="15:55")), 1)
        tr = run(df, sig)
        self.assertEqual(len(tr), 1)                                           # una por día
        self.assertEqual(tr.iloc[0]["entry_time"], pd.Timestamp("2024-03-05 07:40", tz=NY))   # la señal de 7:35 entra a la apertura de las 7:40
        self.assertEqual(tr.iloc[0]["motivo"], "hora")                          # sin regla de salida: cierra a las 15:55

    def test_exit_rule_exits_next_open_and_time_exit_uses_close(self):
        df = add_manuel_indicators(one_day_bars())
        sig = pd.DataFrame({"entry": False, "exit": False}, index=df.index)
        sig.loc[pd.Timestamp("2024-03-05 07:35", tz=NY), "entry"] = True
        sig.loc[pd.Timestamp("2024-03-05 10:00", tz=NY), "exit"] = True
        tr = run(df, sig).iloc[0]
        self.assertEqual((tr["motivo"], tr["exit_time"]), ("regla", pd.Timestamp("2024-03-05 10:05", tz=NY)))
        self.assertAlmostEqual(tr["exit"], df.loc[pd.Timestamp("2024-03-05 10:05", tz=NY), "open"])

    def test_signal_modes_are_mirrors_on_macd_and_stats_handle_small_samples(self):
        df = add_manuel_indicators(one_day_bars())
        a, b = signals(df, "A"), signals(df, "B")
        self.assertFalse((a["entry"] & b["entry"]).any())                       # A y B no pueden cumplirse a la vez
        self.assertEqual(stats(pd.DataFrame({"pts": [1.0], "motivo": ["hora"], "barras": [3]}))["n"], 1)

    def test_no_macd_mode_is_a_superset_and_thresholds_can_loosen(self):
        df = add_manuel_indicators(one_day_bars())
        a, b, n = signals(df, "A"), signals(df, "B"), signals(df, "N")
        self.assertTrue(((a["entry"] | b["entry"]) <= n["entry"]).all())          # sin MACD se cumplen al menos las de A y B
        self.assertGreaterEqual(signals(df, "N", rsi_th=42.0)["entry"].sum(), n["entry"].sum())
        self.assertIn("vwap_sd", df.columns)

    def test_new_exit_x1_leaves_on_first_bearish_bar_below_upper_band_and_x2_waits_for_the_touch(self):
        df = add_manuel_indicators(one_day_bars())
        sig = pd.DataFrame({"entry": False, "exit": False}, index=df.index)
        sig.loc[pd.Timestamp("2024-03-05 07:35", tz=NY), "entry"] = True
        # barras de prueba: una barra roja justo después de entrar, y más tarde el precio toca la banda alta y cierra una roja debajo
        df = df.copy()
        i0 = df.index.get_loc(pd.Timestamp("2024-03-05 07:40", tz=NY))
        df.iloc[i0, df.columns.get_loc("close")] = df.iloc[i0]["open"] - 1.0            # barra bajista en la propia barra de entrada
        df["vwap_up"] = df["close"].max() + 50.0                                         # banda alta lejana: cualquier barra roja cierra debajo
        x1 = run(df, sig, exit_mode="X1").iloc[0]
        self.assertEqual(x1["exit_time"], pd.Timestamp("2024-03-05 07:45", tz=NY))       # sale en la apertura de la barra siguiente
        x2 = run(df, sig, exit_mode="X2").iloc[0]
        self.assertEqual(x2["motivo"], "hora")                                           # el precio nunca tocó la banda: no hay rechazo, cierra a las 15:55
        k = df.index.get_loc(pd.Timestamp("2024-03-05 11:00", tz=NY))
        df.iloc[k, df.columns.get_loc("high")] = df["vwap_up"].iloc[k] + 1.0              # toca la banda alta
        df.iloc[k, df.columns.get_loc("open")] = df.iloc[k]["close"] + 2.0                # y la barra es bajista (cierra debajo de la apertura y de la banda)
        x2b = run(df, sig, exit_mode="X2").iloc[0]
        self.assertEqual((x2b["motivo"], x2b["exit_time"]), ("regla", pd.Timestamp("2024-03-05 11:05", tz=NY)))

    def test_costs_per_instrument(self):
        pts, pv = costs("ES")
        self.assertAlmostEqual(pts * pv, 29.0)
        self.assertAlmostEqual(costs("NQ")[0] * costs("NQ")[1], 14.0)
        self.assertAlmostEqual(costs("YM")[0] * costs("YM")[1], 14.0)
        tr = pd.DataFrame({"pts": [10.0] * 10, "motivo": ["hora"] * 10, "barras": [5] * 10})
        self.assertAlmostEqual(stats(tr, "NQ")["total_usd_neto"], (10 - costs("NQ")[0]) * 20 * 10, places=0)

    def test_placebo_returns_a_probability(self):
        df = add_manuel_indicators(one_day_bars())
        trades = pd.DataFrame({"date": [pd.Timestamp("2024-03-05").date()], "barras": [10], "pts": [2.0]})
        r = placebo(df, trades, n_perm=20)
        self.assertTrue(0.0 <= r["p_valor"] <= 1.0)


if __name__ == "__main__":
    unittest.main()
