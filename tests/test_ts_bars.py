import json
import tempfile
import time
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from bot.ts_bars import TokenError, detect_stamp, download_bars, parse_bars, read_token, to_tradestation_csv

NY = "America/New_York"


def make_payload(start_utc, n):
    idx = pd.date_range(start_utc, periods=n, freq="5min", tz="UTC")
    px = 5000 + np.cumsum(np.random.default_rng(1).choice([-0.5, -0.25, 0.25, 0.5, 0.75], n))
    return [{"TimeStamp": t.strftime("%Y-%m-%dT%H:%M:%SZ"), "Open": str(p), "High": str(p + 0.5), "Low": str(p - 0.5), "Close": str(p + 0.25),
             "TotalVolume": "100"} for t, p in zip(idx, px)]


class TestTsBars(unittest.TestCase):
    def test_token_is_read_from_file_and_expiry_is_enforced(self):
        p = Path(tempfile.mkdtemp()) / "t.json"
        p.write_text(json.dumps({"access_token": "ABC", "expires_at": time.time() + 600}))
        self.assertEqual(read_token(p), "ABC")
        p.write_text(json.dumps({"access_token": "ABC", "expires_at": time.time() + 30}))
        with self.assertRaises(TokenError):
            read_token(p)

    def test_paging_goes_backwards_and_dedupes(self):
        all_bars = make_payload("2026-10-12 12:00", 600)               # 600 barras
        calls = []

        def fetch(url, token):
            calls.append(url)
            import urllib.parse as up
            last = pd.Timestamp(up.parse_qs(up.urlparse(url).query)["lastdate"][0])
            n = int(up.parse_qs(up.urlparse(url).query)["barsback"][0])
            ok = [b for b in all_bars if pd.Timestamp(b["TimeStamp"]) <= last][-300:]          # la "API" entrega a lo más 300 por llamada
            return 200, {"Bars": ok}
        df = download_bars("@ES", "2026-10-12", "2026-10-14", "tok", fetch=fetch)
        self.assertGreater(len(calls), 1)
        self.assertFalse(df.index.duplicated().any())
        self.assertTrue(df.index.is_monotonic_increasing)

    def test_http_error_is_reported(self):
        with self.assertRaises(RuntimeError):
            download_bars("@ES", "2026-10-12", "2026-10-13", "tok", fetch=lambda u, t: (401, {"Message": "no autorizado"}))

    def test_detects_open_vs_close_stamps_and_writes_loadable_csv(self):
        payload = make_payload("2026-10-13 13:00", 160)                  # 9:00 ET en adelante, sesión larga
        api = parse_bars({"Bars": payload})
        d = tempfile.mkdtemp()
        # referencia buena: mismas barras, índice = hora de INICIO en NY, con otro nivel de precio (otro contrato)
        ref = api.copy()
        ref.index = ref.index.tz_convert(NY)
        ref[["open", "high", "low", "close"]] += 35.0
        self.assertEqual(detect_stamp(api, ref), "open")
        shifted = api.copy()
        shifted.index = shifted.index + pd.Timedelta(minutes=5)          # si la API diera la hora de CIERRE
        self.assertEqual(detect_stamp(shifted, ref), "close")
        n = to_tradestation_csv(api, "open", Path(d) / "out.csv")
        self.assertEqual(n, 160)
        self.assertFalse(api.isna().any().any())                          # (error real encontrado al escribir la prueba: los valores salían NaN)
        raw = pd.read_csv(Path(d) / "out.csv")
        self.assertEqual(list(raw.columns), ["fecha_el", "hora_cierre", "open", "high", "low", "close", "volume"])
        self.assertEqual(int(raw["fecha_el"].iloc[0]), 1261013)           # 2026-10-13
        self.assertEqual(int(raw["hora_cierre"].iloc[0]), 905)            # barra que empieza 9:00 cierra 9:05


if __name__ == "__main__":
    unittest.main()
