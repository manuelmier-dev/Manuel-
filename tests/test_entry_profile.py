import unittest

import numpy as np
import pandas as pd

from bot.entry_profile import HORIZONS, forward_table
from bot.strategy_m import add_manuel_indicators
from test_strategy_m import one_day_bars


class TestEntryProfile(unittest.TestCase):
    def test_forward_returns_mae_mfe_and_close(self):
        df = add_manuel_indicators(one_day_bars())
        j = df.index.get_loc(pd.Timestamp("2024-03-05 08:00", tz="America/New_York"))
        f = forward_table(df, np.array([j])).iloc[0]
        entry = df.iloc[j]["open"]
        self.assertAlmostEqual(f["5 min"], df.iloc[j]["close"] - entry)
        self.assertAlmostEqual(f["15 min"], df.iloc[j + 2]["close"] - entry)
        self.assertAlmostEqual(f["cierre"], df.iloc[-1]["close"] - entry)
        self.assertLessEqual(f["MAE"], 0.0 + 1e-9 + max(0.0, df.iloc[j:]["low"].min() - entry))
        self.assertGreaterEqual(f["MFE"], f["cierre"])
        self.assertEqual(len(HORIZONS), 6)


if __name__ == "__main__":
    unittest.main()
