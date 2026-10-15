import unittest

import numpy as np
import pandas as pd

from bot.zone_study import location_stats


class TestZoneStudy(unittest.TestCase):
    def test_real_levels_beat_chance_when_extremes_cluster_at_level(self):
        rng = np.random.default_rng(0)
        n = 300
        center = pd.Series(5000 + rng.normal(0, 30, n).cumsum())
        em = pd.Series(np.full(n, 30.0))
        off = rng.uniform(0.3, 1.0, n)                               # el nivel está entre 0.3 y 1 EM arriba del precio
        level = center + off * em
        high = level + rng.normal(0, 0.1, n) * em                    # el máximo cae casi exactamente en el nivel
        r = location_stats(high, level, center, em)
        self.assertLess(r["p_valor"], 0.05)
        self.assertGreater(r["dentro_0.25EM_%"], 80)

    def test_no_information_gives_high_p_value(self):
        rng = np.random.default_rng(1)
        n = 300
        center = pd.Series(5000 + rng.normal(0, 30, n).cumsum())
        em = pd.Series(np.full(n, 30.0))
        level = center + rng.uniform(0.3, 1.0, n) * em
        high = center + rng.uniform(0.0, 1.5, n) * em                # el máximo no tiene que ver con el nivel
        r = location_stats(high, level, center, em)
        self.assertGreater(r["p_valor"], 0.05)

    def test_level_table_puts_oi_walls_in_es_coordinates(self):
        # error real encontrado en la primera corrida: los walls de OI venían en SPX y se medían contra precios de ES (20 EM de distancia)
        from bot.zone_study import level_table
        days = pd.DataFrame({"gex_bn": [1.0], "em_pts": [20.0], "call_wall": [5040.0], "put_wall": [4980.0], "basis": [60.0],
                             "center_spx": [5000.0]}, index=[pd.Timestamp("2024-01-03").date()])
        summ = pd.DataFrame({"date": [pd.Timestamp("2024-01-03")], "call_wall_gex": [5050.0], "put_wall_gex": [4970.0],
                             "call_wall_oi": [5100.0], "put_wall_oi": [4900.0]})
        lv = level_table(summ, days).iloc[0]
        self.assertEqual((lv["call_oi_1em"], lv["put_oi_1em"], lv["call_gex"], lv["call_oi_global"], lv["mas_1_em"]),
                         (5100.0, 5040.0, 5110.0, 5160.0, 5080.0))

    def test_small_sample_is_reported_not_forced(self):
        s = pd.Series(np.arange(10.0))
        self.assertEqual(location_stats(s, s, s, s + 1)["dias"], 10)


if __name__ == "__main__":
    unittest.main()
