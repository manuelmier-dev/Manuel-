"""Baja barras de 5 minutos de ES de la API de TradeStation y las guarda en el mismo formato que ExportBarras5min.txt.

Uso (en el servidor donde está ts_tokens.json; el token se LEE del archivo, nunca se imprime ni se pide):
  python -m bot.ts_bars probe    <ts_tokens.json> [@ES]                                  # 20 barras de prueba (datos de mercado)
  python -m bot.ts_bars download <ts_tokens.json> <salida.csv> <desde> <hasta> [@ES] [<ES_5min.csv de referencia> | close | open]

*** NO PROBADO contra la API real: Claude no tiene acceso a TradeStation. Los nombres de parámetros salen de la documentación pública
*** (barcharts de la API v3). `probe` guarda la respuesta real para ajustar. Con una referencia (el ES_5min.csv bueno) se comprueba si la
*** hora de la API es la de INICIO o la de CIERRE de la barra, comparando los cambios de precio barra a barra.
"""
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd

BASE = "https://api.tradestation.com/v3/marketdata/barcharts"
NY = "America/New_York"
MAX_BARS = 57600                                  # tope de la API para barras intradía
BAR_MIN = 5


class TokenError(RuntimeError):
    pass


def read_token(path, min_valid_s: int = 120, now=time.time) -> str:
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    tok = d.get("access_token")
    if not tok:
        raise TokenError("El archivo no trae access_token")
    left = float(d.get("expires_at", 0)) - now()
    if left < min_valid_s:
        raise TokenError(f"El token vence en {left:.0f} s (o ya venció). Espera a que el servidor lo renueve y repite.")
    return tok


def fetch_json(url: str, token: str, timeout: int = 120) -> tuple[int, dict]:
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        try:
            return e.code, json.loads(body)
        except ValueError:
            return e.code, {"raw": body[:300]}


def build_url(symbol: str, last_utc: pd.Timestamp, barsback: int = MAX_BARS) -> str:
    q = {"interval": BAR_MIN, "unit": "Minute", "barsback": barsback, "lastdate": last_utc.strftime("%Y-%m-%dT%H:%M:%SZ")}
    return f"{BASE}/{urllib.parse.quote(symbol, safe='')}?{urllib.parse.urlencode(q)}"


def parse_bars(payload: dict) -> pd.DataFrame:
    rows = payload.get("Bars") or []
    if not rows:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    df = pd.DataFrame(rows)
    idx = pd.to_datetime(df["TimeStamp"], utc=True)
    out = pd.DataFrame({"open": df["Open"].astype(float).values, "high": df["High"].astype(float).values,
                        "low": df["Low"].astype(float).values, "close": df["Close"].astype(float).values,
                        "volume": df["TotalVolume"].astype(float).values}, index=pd.DatetimeIndex(idx))
    return out.sort_index()


def download_bars(symbol: str, start, end, token: str, fetch=fetch_json, max_calls: int = 60) -> pd.DataFrame:
    """Pide hacia atrás desde `end` hasta cubrir `start`. Índice en UTC con la hora que entrega la API."""
    start_utc = pd.Timestamp(start).tz_localize(NY).tz_convert("UTC")
    cursor = (pd.Timestamp(end).tz_localize(NY) + pd.Timedelta(days=1)).tz_convert("UTC")
    frames = []
    for _ in range(max_calls):
        status, payload = fetch(build_url(symbol, cursor), token)
        if status != 200:
            raise RuntimeError(f"La API respondió {status}: {str(payload)[:300]}")
        df = parse_bars(payload)
        if df.empty:
            break
        frames.append(df)
        oldest = df.index.min()
        if oldest <= start_utc:
            break
        cursor = oldest - pd.Timedelta(seconds=1)
    if not frames:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    out = pd.concat(frames).sort_index()
    out = out[~out.index.duplicated(keep="last")]
    return out[(out.index >= start_utc) & (out.index < (pd.Timestamp(end).tz_localize(NY) + pd.Timedelta(days=1)).tz_convert("UTC"))]


def detect_stamp(api: pd.DataFrame, ref_open_ny: pd.DataFrame) -> str:
    """¿La hora de la API es la de INICIO ('open') o la de CIERRE ('close') de la barra? Se compara contra la referencia buena
    (índice = hora de inicio) usando el cambio de precio de cierre entre barras, que no depende del contrato (@ES vs ESZ26)."""
    a = api.copy()
    a.index = a.index.tz_convert(NY)
    best, best_share = None, -1.0
    for name, shift in (("open", pd.Timedelta(0)), ("close", pd.Timedelta(minutes=BAR_MIN))):
        idx = a.index - shift
        d_api = pd.Series(a["close"].values, index=idx).diff()
        d_ref = ref_open_ny["close"].diff()
        j = pd.concat([d_api.rename("a"), d_ref.rename("r")], axis=1, join="inner").dropna()
        j = j[(j["r"].abs() > 0)]
        share = float(((j["a"] - j["r"]).abs() < 0.26).mean()) if len(j) >= 50 else 0.0
        if share > best_share:
            best, best_share = name, share
    if best_share < 0.8:
        raise ValueError(f"Las barras de la API no coinciden con la referencia (mejor coincidencia {best_share:.0%}). Revisa el símbolo o la zona horaria.")
    return best


def to_tradestation_csv(api: pd.DataFrame, stamp: str, path) -> int:
    """Escribe fecha_el,hora_cierre,open,high,low,close,volume en hora de Nueva York (hora de CIERRE de la barra)."""
    ny = api.copy()
    ny.index = ny.index.tz_convert(NY)
    close_ts = ny.index + (pd.Timedelta(minutes=BAR_MIN) if stamp == "open" else pd.Timedelta(0))
    out = pd.DataFrame({
        "fecha_el": (close_ts.year - 1900) * 10000 + close_ts.month * 100 + close_ts.day,
        "hora_cierre": close_ts.hour * 100 + close_ts.minute,
        "open": ny["open"].values, "high": ny["high"].values, "low": ny["low"].values, "close": ny["close"].values,
        "volume": ny["volume"].values.astype("int64")})
    out.to_csv(path, index=False)
    return len(out)


if __name__ == "__main__":
    cmd = sys.argv[1]
    token = read_token(sys.argv[2])
    if cmd == "probe":
        sym = sys.argv[3] if len(sys.argv) > 3 else "@ES"
        status, payload = fetch_json(build_url(sym, pd.Timestamp.now(tz="UTC"), barsback=20), token)
        print(f"HTTP {status}; llaves de la respuesta: {list(payload)[:8]}")
        for b in (payload.get("Bars") or [])[-5:]:
            print({k: b[k] for k in ("TimeStamp", "Open", "High", "Low", "Close", "TotalVolume") if k in b})
        if status != 200:
            print(str(payload)[:400])
    elif cmd == "download":
        out_csv, start, end = sys.argv[3], sys.argv[4], sys.argv[5]
        sym = sys.argv[6] if len(sys.argv) > 6 else "@ES"
        ref = sys.argv[7] if len(sys.argv) > 7 else None
        bars = download_bars(sym, start, end, token)
        print(f"Barras recibidas: {len(bars)}  ({bars.index.min()} -> {bars.index.max()})")
        stamp = "open"
        if ref in ("close", "open"):                  # para tramos de años que no se traslapan con la referencia: ya se comprobó que la API da la hora de CIERRE
            stamp = ref
            print(f"Se usa la hora de {'CIERRE' if ref == 'close' else 'INICIO'} de la barra (indicada a mano).")
        elif ref:
            from .journal import load_es_bars_csv
            stamp = detect_stamp(bars, load_es_bars_csv(ref))
            print(f"La hora de la API es la de {'INICIO' if stamp == 'open' else 'CIERRE'} de la barra (comprobado contra {Path(ref).name})")
        else:
            print("Sin referencia: se asume hora de INICIO de la barra (lo que dice la documentación). Verifica con la referencia.")
        print(f"Guardadas {to_tradestation_csv(bars, stamp, out_csv)} barras en {out_csv}")
