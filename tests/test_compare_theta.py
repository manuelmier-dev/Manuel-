import unittest

import pandas as pd

from bot.compare_theta import compare


class TestCompare(unittest.TestCase):
    def test_same_and_different_days(self):
        t = pd.DataFrame({"date": ["2026-10-01", "2026-10-02", "2026-10-03", "2026-10-06"], "gex_bn": [1.0, -2.0, 0.5, 3.0],
                          "call_wall_oi": [5000, 5010, 5020, 5030], "spot": [4990.0, 5000, 5005, 5010]})
        s = pd.DataFrame({"date": ["2026-10-01", "2026-10-02", "2026-10-03", "2026-10-09"], "gex_bn": [1.1, -1.8, 0.6, 9.0],
                          "call_wall_oi": [5000, 5000, 5020, 5030], "spot": [4990.0, 5000, 5005, 5010]})
        d, lines = compare(t, s)
        self.assertEqual(len(d), 3)                                   # solo los días comunes
        text = " ".join(lines)
        self.assertIn("mismo strike en 2 de 3", text)
        self.assertIn("mismo signo (reversión/tendencia) en 3 de 3", text)


if __name__ == "__main__":
    unittest.main()
