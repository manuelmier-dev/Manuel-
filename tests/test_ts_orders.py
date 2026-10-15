import unittest
from datetime import date

from bot.ts_orders import SIM_BASE, SafetyError, assert_sim_account, es_front_symbol, list_accounts, order_body, third_friday


class TestTsOrders(unittest.TestCase):
    def test_only_simulator_host_and_sim_accounts(self):
        self.assertTrue(SIM_BASE.startswith("https://sim-api."))
        self.assertEqual(assert_sim_account("SIM1234567F"), "SIM1234567F")
        with self.assertRaises(SafetyError):
            assert_sim_account("123456782")                         # cuenta real: jamás
        with self.assertRaises(SafetyError):
            order_body("123456782", "ESZ26", "BUY", "Market")

    def test_quantity_is_capped_at_one_contract(self):
        with self.assertRaises(SafetyError):
            order_body("SIM1", "ESZ26", "BUY", "Market", qty=2)
        b = order_body("SIM1", "ESZ26", "SELL", "Limit", limit=7700.123)
        self.assertEqual((b["Quantity"], b["LimitPrice"], b["TradeAction"]), ("1", "7700.12", "SELL"))
        self.assertEqual(order_body("SIM1", "ESZ26", "SELL", "StopMarket", stop=7750.0)["StopPrice"], "7750.00")

    def test_front_month_and_roll(self):
        self.assertEqual(third_friday(2026, 12), date(2026, 12, 18))
        self.assertEqual(es_front_symbol(date(2026, 10, 15)), "ESZ26")
        self.assertEqual(es_front_symbol(date(2026, 9, 8)), "ESU26")                 # antes de la rodada
        self.assertEqual(es_front_symbol(date(2026, 9, 11)), "ESZ26")                # 7 días antes del 18-sep: ya rodó
        self.assertEqual(es_front_symbol(date(2026, 12, 15)), "ESH27")

    def test_list_accounts_reports_errors(self):
        self.assertEqual(list_accounts("t", fetch=lambda m, p, t: (200, {"Accounts": [{"AccountID": "SIM1"}]}))[0]["AccountID"], "SIM1")
        with self.assertRaises(RuntimeError):
            list_accounts("t", fetch=lambda m, p, t: (401, {"Message": "x"}))


if __name__ == "__main__":
    unittest.main()
