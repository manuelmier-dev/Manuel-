import unittest
from datetime import date

from bot.ts_orders import SIM_BASE, far_limit_price, probar_ciclo, SafetyError, assert_sim_account, es_front_symbol, list_accounts, order_body, third_friday


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

    def test_far_limit_price_is_far_below_and_on_tick(self):
        p = far_limit_price(7743.13)
        self.assertEqual(p, 7443.25)
        self.assertEqual(p % 0.25, 0.0)

    def test_ciclo_without_enviar_sends_nothing_and_with_enviar_places_checks_and_cancels(self):
        calls = []

        def fake(method, path, token, body=None):
            calls.append((method, path))
            if method == "POST":
                return 200, {"Orders": [{"OrderID": "99", "Message": "Sent order"}]}
            if method == "DELETE":
                return 200, {"OrderID": "99", "Message": "Sent cancel"}
            state = "ACK" if len([c for c in calls if c[0] == "GET"]) == 1 else "CAN"
            return 200, {"Orders": [{"OrderID": "99", "Status": state, "StatusDescription": state}]}
        log = probar_ciclo("t", "SIM1", 7700.0, date(2026, 10, 15), send=False, fetch=fake)
        self.assertEqual(calls, [])
        self.assertIn("NO se envía", log[-1])
        log = probar_ciclo("t", "SIM1", 7700.0, date(2026, 10, 15), send=True, fetch=fake)
        self.assertEqual([c[0] for c in calls], ["POST", "GET", "DELETE", "GET"])
        self.assertIn("Estado final: CAN", log[-1])
        with self.assertRaises(SafetyError):
            probar_ciclo("t", "123456", 7700.0, date(2026, 10, 15), send=True, fetch=fake)      # cuenta real: nunca

    def test_rejected_order_raises(self):
        from bot.ts_orders import place_order
        with self.assertRaises(RuntimeError):
            place_order("t", order_body("SIM1", "ESZ26", "BUY", "Limit", limit=7000.0), fetch=lambda *a, **k: (400, {"Message": "no"}))

    def test_list_accounts_reports_errors(self):
        self.assertEqual(list_accounts("t", fetch=lambda m, p, t: (200, {"Accounts": [{"AccountID": "SIM1"}]}))[0]["AccountID"], "SIM1")
        with self.assertRaises(RuntimeError):
            list_accounts("t", fetch=lambda m, p, t: (401, {"Message": "x"}))


if __name__ == "__main__":
    unittest.main()
