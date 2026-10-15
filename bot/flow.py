"""Flujo con signo de las operaciones SPXW 0DTE (primera hora) -> presión de cobertura de los market makers.

Uso (en el servidor con Theta Terminal, FUERA de horario):
  python -m bot.flow <carpeta_salida> <theta_resumen.csv> <barras_ES.csv> <desde> <hasta> [--max-min 600]
Baja trade_quote de 9:30 a 10:30 en tramos de 5 min, calcula agregados por tramo y guarda flow/AAAA-MM-DD.csv. Reanuda.

*** Es un PROXY: el signo se infiere (precio >= ask: cliente compra; <= bid: cliente vende; entre medio: no se clasifica).
Se supone que el cliente es el agresor y el market maker la contraparte. El inventario real del dealer no es observable.
"""
import sys
import time
from math import pi, sqrt
from pathlib import Path

import numpy as np
import pandas as pd

from .theta_client import ThetaError, _col, _right, _strike, fetch_text, get_frame, ymd

NY = "America/New_York"
SLICES = [(f"{9 + (30 + 5 * k) // 60:02d}:{(30 + 5 * k) % 60:02d}:00", f"{9 + (35 + 5 * k) // 60:02d}:{(35 + 5 * k) % 60:02d}:00") for k in range(12)]
FEATURES = ["bucket", "n_trades", "vol", "vol_clasif", "cust_buy_c", "cust_sell_c", "cust_buy_p", "cust_sell_p",
            "dealer_delta", "dealer_gamma", "spot"]


def _ncdf(x):
    """Normal acumulada (Abramowitz-Stegun 7.1.26 sobre erf), vectorizada, error < 1e-7."""
    z = np.abs(x) / sqrt(2.0)
    t = 1.0 / (1.0 + 0.3275911 * z)
    erf = 1 - (((((1.061405429 * t - 1.453152027) * t) + 1.421413741) * t - 0.284496736) * t + 0.254829592) * t * np.exp(-z * z)
    return 0.5 * (1 + np.where(x >= 0, erf, -erf))


def bs_price(spot, k, t, vol, is_call):
    sd = vol * np.sqrt(t)
    d1 = (np.log(spot / k) + 0.5 * sd * sd) / sd
    d2 = d1 - sd
    return np.where(is_call, spot * _ncdf(d1) - k * _ncdf(d2), k * _ncdf(-d2) - spot * _ncdf(-d1))


def implied_vol(price, spot, k, t, is_call, lo=0.02, hi=5.0, iters=40):
    """Bisección vectorizada (tasa 0). NaN si el precio no cabe entre vol 2% y 500% (por debajo del valor intrínseco, etc.)."""
    price, spot, k, t = (np.asarray(a, float) for a in (price, spot, k, t))
    a, b = np.full(price.shape, lo), np.full(price.shape, hi)
    for _ in range(iters):
        m = (a + b) / 2
        up = bs_price(spot, k, t, m, is_call) < price
        a, b = np.where(up, m, a), np.where(up, b, m)
    v = (a + b) / 2
    ok = (price > bs_price(spot, k, t, np.full(price.shape, lo), is_call)) & (price < bs_price(spot, k, t, np.full(price.shape, hi), is_call))
    return np.where(ok, v, np.nan)


def delta_gamma(spot, k, t, vol, is_call):
    sd = vol * np.sqrt(t)
    d1 = (np.log(spot / k) + 0.5 * sd * sd) / sd
    delta = np.where(is_call, _ncdf(d1), _ncdf(d1) - 1)
    gamma = np.exp(-0.5 * d1 * d1) / sqrt(2 * pi) / (spot * sd)
    return delta, gamma


def normalize_trades(df: pd.DataFrame, day) -> pd.DataFrame:
    """Columnas de trade_quote -> ts (NY), strike, right, size, price, bid, ask."""
    ts = pd.to_datetime(df[_col(df, "trade_timestamp", "timestamp")]).dt.tz_localize(NY, ambiguous="NaT", nonexistent="NaT")
    out = pd.DataFrame({"ts": ts, "strike": _strike(df[_col(df, "strike")]), "right": _right(df[_col(df, "right")]),
                        "size": pd.to_numeric(df[_col(df, "size")], errors="coerce"),
                        "price": pd.to_numeric(df[_col(df, "price")], errors="coerce"),
                        "bid": pd.to_numeric(df[_col(df, "bid")], errors="coerce"),
                        "ask": pd.to_numeric(df[_col(df, "ask")], errors="coerce")})
    return out.dropna(subset=["ts", "strike", "size", "price"]).query("size > 0")


def sign_trades(tr: pd.DataFrame) -> pd.Series:
    """+1 el cliente compra (precio >= ask), -1 vende (precio <= bid), 0 sin clasificar (entre medio, cotización inválida o cruzada)."""
    valid = (tr["bid"] > 0) & (tr["ask"] > tr["bid"])
    s = np.where(valid & (tr["price"] >= tr["ask"]), 1, np.where(valid & (tr["price"] <= tr["bid"]), -1, 0))
    return pd.Series(s, index=tr.index)


def bucket_features(tr: pd.DataFrame, spot_at, close=pd.Timestamp("16:00").time()) -> pd.DataFrame:
    """Agregados por tramo de 5 min. spot_at(ts)->float (SPX estimado). dealer_* = -(signo del cliente) x tamaño x griega x 100:
    dealer_delta > 0 => los dealers quedan largos delta (cliente vendió calls/compró puts) y venden futuros para cubrirse
    (presión BAJISTA); < 0 => compran futuros (alcista). Se muestra con ese signo SIN invertir; la regla decide la dirección."""
    if tr.empty:
        return pd.DataFrame(columns=FEATURES)
    tr = tr.copy()
    tr["sign"] = sign_trades(tr)
    tr["spot"] = [spot_at(t) for t in tr["ts"]]
    day_close = tr["ts"].dt.normalize() + pd.Timedelta(hours=16)
    tr["t"] = ((day_close - tr["ts"]).dt.total_seconds().clip(lower=60)) / (365 * 24 * 3600)
    is_call = (tr["right"] == "C").to_numpy()
    vol = implied_vol(tr["price"].to_numpy(), tr["spot"].to_numpy(), tr["strike"].to_numpy(), tr["t"].to_numpy(), is_call)
    d, g = delta_gamma(tr["spot"].to_numpy(), tr["strike"].to_numpy(), tr["t"].to_numpy(), np.where(np.isnan(vol), 0.2, vol), is_call)
    good = ~np.isnan(vol) & (tr["sign"].to_numpy() != 0)
    sz = tr["size"].to_numpy()
    tr["dd"] = np.where(good, -tr["sign"] * sz * d * 100, 0.0)
    tr["dg"] = np.where(good, -tr["sign"] * sz * g * 100, 0.0)
    tr["bucket"] = tr["ts"].dt.floor("5min").dt.strftime("%H:%M")
    tr["vc"] = np.where(tr["sign"] != 0, sz, 0)
    c, p = tr["right"] == "C", tr["right"] == "P"
    tr["bc"], tr["sc"] = np.where(c & (tr["sign"] == 1), sz, 0), np.where(c & (tr["sign"] == -1), sz, 0)
    tr["bp"], tr["sp"] = np.where(p & (tr["sign"] == 1), sz, 0), np.where(p & (tr["sign"] == -1), sz, 0)
    g_ = tr.groupby("bucket")
    return pd.DataFrame({"n_trades": g_.size(), "vol": g_["size"].sum(), "vol_clasif": g_["vc"].sum(),
                         "cust_buy_c": g_["bc"].sum(), "cust_sell_c": g_["sc"].sum(), "cust_buy_p": g_["bp"].sum(),
                         "cust_sell_p": g_["sp"].sum(), "dealer_delta": g_["dd"].sum(), "dealer_gamma": g_["dg"].sum(),
                         "spot": g_["spot"].mean()}).reset_index()[FEATURES]


def make_spot_fn(es: pd.DataFrame, day, spot_920: float, es_close_920: float):
    """SPX(t) ~ spot a las 9:20 + (cierre ES de la última barra cerrada - cierre ES a las 9:20). Sin mirar el futuro."""
    closes = es["close"]
    def f(ts):
        sub = closes.loc[: ts - pd.Timedelta(minutes=5)]
        return spot_920 + (float(sub.iloc[-1]) - es_close_920 if len(sub) else 0.0)
    return f


def day_flow(day, spot_920: float, es: pd.DataFrame, fetch=fetch_text, symbol: str = "SPXW") -> pd.DataFrame:
    d = pd.Timestamp(day)
    done = es.loc[: pd.Timestamp.combine(d.date(), pd.Timestamp("09:20").time()).tz_localize(NY) - pd.Timedelta(minutes=5)]
    if done.empty:
        raise ValueError("sin barra de ES antes de las 9:20")
    spot_fn = make_spot_fn(es, d, spot_920, float(done["close"].iloc[-1]))
    frames = []
    for t0, t1 in SLICES:
        df = get_frame("/option/history/trade_quote", {"symbol": symbol, "expiration": ymd(d), "date": ymd(d), "strike": "*",
                                                       "start_time": t0, "end_time": t1}, fetch)
        if len(df):
            frames.append(normalize_trades(df, d))
    if not frames:
        return pd.DataFrame(columns=FEATURES)
    return bucket_features(pd.concat(frames, ignore_index=True), spot_fn)


def run(out_dir, resumen_csv, es_csv, start, end, max_min: float = 600, fetch=fetch_text, log=print) -> dict:
    from .journal import load_es_bars_csv
    es = load_es_bars_csv(es_csv)
    res = pd.read_csv(resumen_csv, parse_dates=["date"])
    res = res[(res["date"] >= pd.Timestamp(start)) & (res["date"] <= pd.Timestamp(end))].sort_values("date")
    out = Path(out_dir) / "flow"
    out.mkdir(parents=True, exist_ok=True)
    t_start, ok, bad, skip = time.time(), 0, 0, 0
    for _, r in res.iterrows():
        f = out / f"{r['date'].date()}.csv"
        if f.exists():
            skip += 1
            continue
        if (time.time() - t_start) / 60 > max_min:
            log(f"Tiempo máximo ({max_min:.0f} min) alcanzado; vuelve a correr para seguir.")
            break
        t = time.time()
        try:
            day_flow(r["date"], float(r["spot"]), es, fetch).to_csv(f, index=False)
            ok += 1
            log(f"{r['date'].date()} ok en {time.time() - t:.0f}s")
        except (ThetaError, ValueError, KeyError) as e:
            bad += 1
            log(f"{r['date'].date()} FALLÓ: {e}")
    log(f"Listo: {ok} nuevos, {skip} ya estaban, {bad} fallaron.")
    return {"ok": ok, "skip": skip, "bad": bad}


if __name__ == "__main__":
    a = [x for x in sys.argv[1:] if not x.startswith("--")]
    mm = float(sys.argv[sys.argv.index("--max-min") + 1]) if "--max-min" in sys.argv else 600
    if "--max-min" in sys.argv:
        a.remove(sys.argv[sys.argv.index("--max-min") + 1])
    run(a[0], a[1], a[2], a[3], a[4], mm)
