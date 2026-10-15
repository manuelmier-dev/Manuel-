import unittest

import pandas as pd

from bot.trades_report import by_period


class TestTradesReport(unittest.TestCase):
    def test_groups_by_year_and_adds_costs_back(self):
        t = pd.DataFrame({"date": ["2023-02-01", "2023-03-01", "2024-01-05"], "usd": [100.0, -50.0, -50.0]})
        r = by_period(t, "year").set_index("periodo")
        self.assertEqual(r.loc[2023, "operaciones"], 2)
        self.assertEqual(r.loc[2023, "total_usd"], 50.0)
        self.assertEqual(r.loc[2023, "total_antes_de_costos"], 50.0 + 2 * 29)          # 4 de comisión + 25 de deslizamiento por operación
        self.assertEqual(len(by_period(t, "quarter")), 3)


if __name__ == "__main__":
    unittest.main()
