import unittest

from bot.theta_flow_probe import probe, variants


class TestFlowProbe(unittest.TestCase):
    def test_falls_back_to_the_second_form_and_reports_columns(self):
        calls = []

        def fetch(url):
            calls.append(url)
            if "start_date" not in url:
                return 400, "parametro no valido"
            return 200, "symbol,strike,right,trade_timestamp,price,size,bid,ask\nSPXW,7800.000,CALL,2026-10-13T09:30:01,3.0,5,2.9,3.1\n"
        log = "\n".join(probe("2026-10-13", "09:30:00", "09:35:00", fetch=fetch))
        self.assertEqual(len(calls), 2)
        self.assertIn("HTTP 400", log)
        self.assertIn("1 filas", log)
        self.assertIn("Columnas: symbol,strike", log)

    def test_both_variants_use_the_same_day_and_window(self):
        for _, p in variants("2026-10-13", "09:30:00", "09:35:00"):
            self.assertEqual((p["expiration"], p["start_time"], p["end_time"]), ("20261013", "09:30:00", "09:35:00"))


if __name__ == "__main__":
    unittest.main()
