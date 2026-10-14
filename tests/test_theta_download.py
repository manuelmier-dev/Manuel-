import tempfile
import unittest
import urllib.parse
from pathlib import Path
from unittest import mock

import numpy as np
import pandas as pd

from bot.loaders import summarize_folder
from bot.theta_client import ThetaError, build_url, get_frame, normalize_oi, normalize_quotes, open_interest
from bot.theta_download import download_range, expiration_days, load_theta_folder, recompute_from_raw
from test_loaders2 import STRIKES, prices

DAYS = ["2026-10-12", "2026-10-13", "2026-10-14"]


def make_fetch(oi_date_param_works=False, fail_day=None, status_for_all=None):
    call, put, _ = prices()
    calls = []

    def fetch(url):
        calls.append(url)
        if status_for_all:
            return status_for_all, "error"
        path, _, qs = url.partition("?")
        q = {k: v[0] for k, v in urllib.parse.parse_qs(qs).items()}
        if path.endswith("/option/list/expirations"):
            return 200, "symbol,expiration\n" + "\n".join(f"SPXW,{d}" for d in DAYS + ["2026-10-17"])
        exp = q.get("expiration", "")
        if fail_day and exp == fail_day.replace("-", ""):
            return 200, ""                                                       # día sin datos
        if path.endswith("/option/at_time/quote"):
            rows = [f"SPXW,{exp},{k},{r},{b:.2f},{a:.2f}" for r, px in (("CALL", call), ("PUT", put)) for k, b, a in zip(STRIKES, px - .05, px + .05)]
            return 200, "symbol,expiration,strike,right,bid,ask\n" + "\n".join(rows)
        if path.endswith("/option/history/open_interest"):
            if "date" in q and not oi_date_param_works:
                return 400, "parametro date no valido"
            rows = [f"SPXW,{exp},{k},{r},{oi}" for r, oi in (("CALL", 1000), ("PUT", 2000)) for k in STRIKES]
            return 200, "symbol,expiration,strike,right,open_interest\n" + "\n".join(rows)
        return 404, "no existe"
    fetch.calls = calls
    return fetch


class TestClient(unittest.TestCase):
    def test_url_keeps_wildcard_and_colon(self):
        u = build_url("/option/at_time/quote", {"symbol": "SPXW", "strike": "*", "time_of_day": "09:20:00.000"})
        self.assertIn("strike=*", u)
        self.assertIn("time_of_day=09:20:00.000", u)
        self.assertIn("format=csv", u)

    def test_open_interest_falls_back_to_date_range_params(self):
        f = make_fetch(oi_date_param_works=False)
        df = open_interest("SPXW", "2026-10-13", "2026-10-13", f)
        self.assertEqual(len(df), 2 * len(STRIKES))
        self.assertTrue(any("start_date=" in u for u in f.calls))

    def test_session_errors_are_not_retried(self):
        with self.assertRaises(ThetaError) as cm:
            get_frame("/x", {}, lambda url: (478, "INVALID_SESSION_ID"))
        self.assertEqual(cm.exception.status, 478)

    def test_transient_errors_are_retried_then_raise(self):
        n = []
        with mock.patch("bot.theta_client.time.sleep"):
            with self.assertRaises(ThetaError):
                get_frame("/x", {}, lambda url: (n.append(1) or 429, "busy"), tries=3)
        self.assertEqual(len(n), 3)

    def test_normalize_tenths_of_cent_strikes_and_right_names(self):
        q = pd.DataFrame({"Strike": [5000000, 5005000], "Right": ["call", "put"], "Bid": [1.0, 2.0], "Ask": [1.2, 2.2]})
        n = normalize_quotes(q)
        self.assertEqual(list(n["strike"]), [5000.0, 5005.0])
        self.assertEqual(list(n["right"]), ["C", "P"])
        oi = normalize_oi(pd.DataFrame({"strike": [5000, 5000], "right": ["CALL", "CALL"], "open_interest": [10, 20],
                                        "timestamp": ["2026-10-13T06:30:00", "2026-10-13T06:31:00"]}))
        self.assertEqual(len(oi), 1)
        self.assertEqual(oi.iloc[0]["open_interest"], 20)


class TestDownload(unittest.TestCase):
    def run_download(self, d, **kw):
        with mock.patch("bot.theta_client.time.sleep"), mock.patch("bot.theta_download.time.sleep"), \
                mock.patch("bot.theta_download.MIN_STRIKES", 10):        # los datos de prueba tienen 17 strikes; la cadena real, cientos
            return download_range(d, "2026-10-01", "2026-10-31", fetch=make_fetch(**kw), log=lambda *_: None)

    def test_expiration_days_filters_to_dates(self):
        days = expiration_days("SPXW", make_fetch())
        self.assertEqual(len(days), 4)

    def test_download_writes_files_resumes_and_loads(self):
        d = tempfile.mkdtemp()
        r1 = self.run_download(d)
        self.assertEqual((r1["nuevos"], r1["fallidos"]), (3, 0))               # el sábado 17 se ignora
        self.assertTrue((Path(d) / "tables" / "2026-10-13.csv").exists())
        r2 = self.run_download(d)
        self.assertEqual((r2["nuevos"], r2["ya_hechos"]), (0, 3))               # reanuda sin repetir
        df, errors = load_theta_folder(d)
        self.assertEqual(len(df), 3)
        self.assertEqual(errors, [])
        self.assertIsInstance(df.iloc[0]["_table"], pd.DataFrame)
        self.assertEqual(df.iloc[0]["gamma_fuente"], "estimada")
        self.assertTrue(np.isnan(df.iloc[0]["em_tradestation"]))

    def test_raw_tables_are_saved_and_recompute_matches(self):
        d = tempfile.mkdtemp()
        self.run_download(d)
        self.assertTrue((Path(d) / "raw" / "2026-10-13.csv").exists())
        before, _ = load_theta_folder(d)
        self.assertEqual(recompute_from_raw(d), 3)                              # sin llamar a la API
        after, _ = load_theta_folder(d)
        self.assertEqual(len(after), 3)
        self.assertAlmostEqual(before.iloc[0]["spot"], after.iloc[0]["spot"])
        self.assertAlmostEqual(before.iloc[0]["gex_bn"], after.iloc[0]["gex_bn"])

    def test_summarize_folder_dispatches_to_theta_folder(self):
        d = tempfile.mkdtemp()
        self.run_download(d)
        df, _ = summarize_folder(d)
        self.assertEqual(len(df), 3)

    def test_failed_day_is_logged_and_retried_next_time(self):
        d = tempfile.mkdtemp()
        r = self.run_download(d, fail_day="2026-10-13")
        self.assertEqual((r["nuevos"], r["fallidos"]), (2, 1))
        self.assertIn("2026-10-13", (Path(d) / "theta_errores.csv").read_text())
        self.assertFalse((Path(d) / "tables" / "2026-10-13.csv").exists())     # sin tabla: se reintenta en la próxima corrida

    def test_too_few_strikes_is_an_error_not_a_silent_row(self):
        d = tempfile.mkdtemp()
        with mock.patch("bot.theta_client.time.sleep"), mock.patch("bot.theta_download.time.sleep"):
            r = download_range(d, "2026-10-01", "2026-10-31", fetch=make_fetch(), log=lambda *_: None)    # MIN_STRIKES real = 20 > 17
        self.assertEqual((r["nuevos"], r["fallidos"]), (0, 3))
        self.assertIn("strikes con cotización válida", (Path(d) / "theta_errores.csv").read_text())

    def test_session_conflict_stops_everything(self):
        d = tempfile.mkdtemp()
        calls = {"n": 0}
        base = make_fetch()

        def fetch(url):
            if "at_time" in url:
                return 478, "INVALID_SESSION_ID"
            return base(url)
        with mock.patch("bot.theta_client.time.sleep"), mock.patch("bot.theta_download.time.sleep"):
            with self.assertRaises(ThetaError):
                download_range(d, "2026-10-01", "2026-10-31", fetch=fetch, log=lambda *_: None)


if __name__ == "__main__":
    unittest.main()


class TestSpotParityWideChain(unittest.TestCase):
    def test_far_strikes_with_empty_quotes_do_not_fake_the_spot(self):
        from bot.loaders import _spot_by_parity
        k = np.arange(3000.0, 10001.0, 5.0)
        spot = 7700.0
        mid_c, mid_p = np.maximum(spot - k, 0) + 0.05, np.maximum(k - spot, 0) + 0.05      # valor intrínseco + 5 centavos
        near = np.abs(k - spot) < 40
        mid_c[near] += 8 - np.abs(k[near] - spot) / 10
        mid_p[near] += 8 - np.abs(k[near] - spot) / 10
        z = pd.DataFrame({"strike": k, "mid_c": mid_c, "mid_p": mid_p})
        far = (k > 9000) | (k < 4000)                                                       # call y put "iguales" (0.05) lejos del dinero
        z.loc[far, ["mid_c", "mid_p"]] = 0.05
        self.assertAlmostEqual(_spot_by_parity(z), spot, delta=6)
