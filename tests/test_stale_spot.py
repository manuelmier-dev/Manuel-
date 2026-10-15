import unittest

import numpy as np
import pandas as pd

from bot.days import build_days

NY = "America/New_York"


def bars_for(day, prev_close, es_915):
    """Cierre del día anterior (15:55) y barras de 9:00 a 9:30; la de 9:15 cierra en es_915."""
    d = pd.Timestamp(day)
    prev = pd.DataFrame({"open": prev_close, "high": prev_close, "low": prev_close, "close": prev_close, "volume": 1.0},
                        index=[(d - pd.Timedelta(days=1)).replace(hour=15, minute=55).tz_localize(NY)])
    idx = pd.date_range(f"{day} 09:00", f"{day} 09:30", freq="5min", tz=NY)
    px = pd.Series(es_915, index=idx)
    return pd.concat([prev, pd.DataFrame({"open": px, "high": px, "low": px, "close": px, "volume": 1.0})])


def table(call_oi, put_oi):
    strikes = np.arange(4900, 5201, 10.0)
    return pd.DataFrame({"strike": strikes,
                         "oi_c": [call_oi.get(k, 10) for k in strikes], "oi_p": [put_oi.get(k, 10) for k in strikes]})


def row(day, spot, em, t):
    return {"date": pd.Timestamp(day), "snapshot_et": "09:20", "spot": spot, "gex_bn": 2.0, "gex_ratio": 0.1,
            "em_tradestation": em, "em_straddle": em + 5, "call_wall_oi": 5200.0, "put_wall_oi": 4900.0,
            "call_wall_oi_1em": np.nan, "put_wall_oi_1em": np.nan, "call_wall_gex": 5100.0, "put_wall_gex": 5000.0, "_table": t}


class TestStaleSpot(unittest.TestCase):
    def test_base_comes_from_previous_close_and_walls_are_centered_on_real_price(self):
        # spot del archivo = cierre viejo 5000; ES cerró ayer en 5050 (base 50); ES a las 9:15 = 5080 (salto +30)
        # precio real a las 9:20 en SPX = 5080 - 50 = 5030; EM = 40 -> calls en [5030, 5070], puts en [4990, 5030]
        t = table({5010.0: 9000, 5040.0: 4000, 5200.0: 20000}, {5000.0: 5000, 5020.0: 3000, 4900.0: 20000})
        days, skipped = build_days(pd.DataFrame([row("2024-01-03", 5000.0, 40.0, t)]), bars_for("2024-01-03", 5050.0, 5080.0))
        self.assertEqual(skipped, [])
        r = days.iloc[0]
        self.assertEqual(r["basis"], 50.0)
        self.assertEqual(r["center_spx"], 5030.0)
        self.assertEqual(r["gap_nocturno"], 30.0)
        self.assertEqual(r["call_wall"], 5040.0)     # 5010 tiene más OI pero queda debajo del precio real; 5200 está fuera de ±1 EM
        self.assertEqual(r["put_wall"], 5000.0)      # entre 4990 y 5030 el mayor OI de puts es 5000

    def test_theta_spot_is_live_so_it_is_the_center_and_the_base_uses_es_915(self):
        # Theta: el spot de las 9:20 ya es el precio real (5030). ES a las 9:15 = 5080 -> base 50, sin usar el cierre previo (5050 sería base 20)
        t = table({5040.0: 4000}, {5000.0: 5000})
        r0 = row("2024-01-03", 5030.0, 40.0, t)
        r0["fuente"] = "theta"
        days, skipped = build_days(pd.DataFrame([r0]), bars_for("2024-01-03", 5050.0, 5080.0))
        self.assertEqual(skipped, [])
        r = days.iloc[0]
        self.assertEqual((r["center_spx"], r["basis"]), (5030.0, 50.0))
        self.assertEqual(r["gap_nocturno"], 30.0)

    def test_theta_day_accepts_adjusted_es_with_huge_base_and_rejects_a_wild_jump(self):
        t = table({5040.0: 4000}, {5000.0: 5000})
        days = []
        for i, base in enumerate([888.0, 889.0, 890.0, 400.0]):             # ES "continuo ajustado": base ~890; el último día es un salto absurdo
            day = f"2024-01-0{2 + i}"
            r0 = row(day, 5030.0, 40.0, t)
            r0["fuente"] = "theta"
            days.append((r0, bars_for(day, 5900.0, 5030.0 + base)))
        summary = pd.DataFrame([a for a, _ in days])
        bars = pd.concat([b for _, b in days]).sort_index()
        bars = bars[~bars.index.duplicated(keep="last")]
        out, skipped = build_days(summary, bars)
        self.assertEqual(len(out), 3)
        self.assertAlmostEqual(out.iloc[0]["basis"], 888.0)
        self.assertEqual(len(skipped), 1)
        self.assertIn("saltó", skipped[0])

    def test_global_oi_mode_keeps_file_walls(self):
        t = table({}, {})
        days, _ = build_days(pd.DataFrame([row("2024-01-03", 5000.0, 40.0, t)]), bars_for("2024-01-03", 5050.0, 5080.0), wall_mode="oi")
        self.assertEqual((days.iloc[0]["call_wall"], days.iloc[0]["put_wall"]), (5200.0, 4900.0))

    def test_no_oi_in_range_gives_nan_walls_and_skips_if_both_missing(self):
        t = table({k: 0 for k in np.arange(4900, 5201, 10.0)}, {k: 0 for k in np.arange(4900, 5201, 10.0)})
        days, skipped = build_days(pd.DataFrame([row("2024-01-03", 5000.0, 40.0, t)]), bars_for("2024-01-03", 5050.0, 5080.0))
        self.assertTrue(days.empty)
        self.assertIn("sin wall", skipped[0])

    def test_missing_previous_close_skips_day(self):
        bars = bars_for("2024-01-03", 5050.0, 5080.0).iloc[1:]       # sin la barra del cierre previo
        days, skipped = build_days(pd.DataFrame([row("2024-01-03", 5000.0, 40.0, table({}, {}))]), bars)
        self.assertTrue(days.empty)
        self.assertIn("cierre de ES del día anterior", skipped[0])

    def test_carry_is_smoothed_with_rolling_median(self):
        rows, bars = [], []
        for d, spot in [("2024-01-02", 5000.0), ("2024-01-03", 5000.0), ("2024-01-04", 4950.0)]:   # el tercer día trae un spot raro
            rows.append(row(d, spot, 40.0, table({5040.0: 100}, {4980.0: 100})))
            bars.append(bars_for(d, 5050.0, 5050.0))
        bars_all = pd.concat(bars)
        bars_all = bars_all[~bars_all.index.duplicated(keep="last")].sort_index()
        days, _ = build_days(pd.DataFrame(rows), bars_all)
        self.assertEqual(list(days["basis"]), [50.0, 50.0, 50.0])     # mediana de 50, 50, 100 = 50


if __name__ == "__main__":
    unittest.main()
