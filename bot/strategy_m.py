"""Estrategia de don Manuel (15-oct-2026): compra de reversión en pre-mercado con MACD (histograma), RSI y VWAP con bandas. Solo ES, sin opciones.

Uso:  python -m bot.strategy_m <barras1.csv> [<barras2.csv> ...]

Reglas tal como las dio don Manuel + SUPUESTOS (marcados) para lo que no dijo. Todo fijado antes de ver resultados:
  Gráfica de 5 minutos, ES 24 horas. MACD (12, 26, 9) en histograma, RSI (14), VWAP de la sesión Globex (reinicia 18:00 NY) con bandas de +-2 desviaciones.
  ENTRADA (compra): ventana = hasta 2 horas antes de la apertura americana (7:30 a 9:30 NY). Al CIERRE de una barra se cumple:
     - RSI de la barra anterior < 33 y el RSI sube respecto a esa barra ("después de llegar a menos de 33")        [SUPUESTO: "llegar" = la barra anterior]
     - cierre por debajo de la banda baja del VWAP y la barra sube (cierre > apertura)
     - MACD: modo A (literal): histograma MENOR que el de la barra anterior;  modo B (alternativa): histograma MAYOR (se acorta si es rojo)
     Entra a mercado en la APERTURA de la siguiente barra [SUPUESTO: no se puede ver "dentro de la barra" con datos de 5 min]. Una entrada por día [SUPUESTO].
  SALIDA: al cierre de una barra se cumplen TODAS: banda alta del VWAP subiendo, el precio la cruza hacia abajo (cierre anterior >= banda, cierre actual < banda),
     MACD en verde (histograma > 0) y menor que el de la barra anterior, RSI bajando y por debajo de 70. Sale a mercado en la apertura de la siguiente barra.
     [SUPUESTO: salida de seguridad a las 15:55 NY, sin stop de pérdida porque no lo pidió.]
  Costo: 29 USD por operación (0.58 pts). 1 contrato.
Se compara contra un PLACEBO: la misma cantidad de días con entrada en una barra al azar de la misma ventana y la misma duración de la operación.
"""
import sys

import numpy as np
import pandas as pd

from .hyp_test import COST_PTS
from .indicators import rsi
from .journal import load_es_bars_csv

NY = "America/New_York"
WIN_START, WIN_END = "07:30", "09:30"          # barras de ENTRADA: inicio >= 7:30 y < 9:30
FLAT = "15:55"


def add_manuel_indicators(bars: pd.DataFrame) -> pd.DataFrame:
    df = bars.copy()
    c = df["close"]
    macd = c.ewm(span=12, adjust=False).mean() - c.ewm(span=26, adjust=False).mean()
    df["hist"] = macd - macd.ewm(span=9, adjust=False).mean()
    df["rsi"] = rsi(c, 14)
    sess = (df.index - pd.Timedelta(hours=18)).date                      # la sesión Globex empieza a las 18:00 NY del día anterior
    g = pd.Series(sess, index=df.index)
    tp = (df["high"] + df["low"] + df["close"]) / 3
    v = df["volume"].astype(float)
    cv = v.groupby(g).cumsum().replace(0, np.nan)
    vwap = (tp * v).groupby(g).cumsum() / cv
    sd = np.sqrt((((tp**2) * v).groupby(g).cumsum() / cv - vwap**2).clip(lower=0))
    df["vwap"], df["vwap_up"], df["vwap_dn"] = vwap, vwap + 2 * sd, vwap - 2 * sd
    return df


def signals(df: pd.DataFrame, mode: str = "A") -> pd.DataFrame:
    h, hp = df["hist"], df["hist"].shift(1)
    r, rp = df["rsi"], df["rsi"].shift(1)
    macd_ok = (h < hp) if mode == "A" else (h > hp)
    entry = (rp < 33) & (r > rp) & (df["close"] < df["vwap_dn"]) & (df["close"] > df["open"]) & macd_ok
    up, upp, cp = df["vwap_up"], df["vwap_up"].shift(1), df["close"].shift(1)
    exit_ = (up > upp) & (cp >= upp) & (df["close"] < up) & (h > 0) & (h < hp) & (r < rp) & (r < 70)
    return pd.DataFrame({"entry": entry.fillna(False), "exit": exit_.fillna(False)})


def run(df: pd.DataFrame, sig: pd.DataFrame) -> pd.DataFrame:
    """Una entrada por día en la ventana; sale por la regla o a las 15:55. Devuelve las operaciones (en puntos, sin costos)."""
    t = df.index
    mins = np.array(t.hour * 60 + t.minute)
    day = np.array(t.date)
    o, c = df["open"].to_numpy(), df["close"].to_numpy()
    e_arr, x_arr = sig["entry"].to_numpy(), sig["exit"].to_numpy()
    w0, w1, fl = 7 * 60 + 30, 9 * 60 + 30, 15 * 60 + 55
    n = len(df)
    trades, last_day = [], None
    for i in np.flatnonzero(e_arr):
        j = i + 1                                             # entrada en la apertura de la barra siguiente
        if j >= n or (t[j] - t[i]) != pd.Timedelta(minutes=5) or day[j] != day[i]:
            continue
        if not (w0 <= mins[j] < w1) or day[j] == last_day:
            continue
        last_day = day[j]
        k = j
        while True:                                           # recorre barras del mismo día
            if mins[k] >= fl or k + 1 >= n or day[k + 1] != day[k]:
                xp, why, kx = c[k], "hora", k
                break
            if x_arr[k] and k >= j:
                xp, why, kx = o[k + 1], "regla", k + 1
                break
            k += 1
        trades.append({"date": day[j], "entry_time": t[j], "exit_time": t[kx], "entry": o[j], "exit": xp, "pts": xp - o[j], "motivo": why, "barras": kx - j})
    return pd.DataFrame(trades)


def placebo(df: pd.DataFrame, trades: pd.DataFrame, n_perm: int = 500, seed: int = 9) -> dict:
    """Misma cantidad de días, entrada en una barra al azar de la ventana, misma duración. ¿La regla gana más que entrar al azar?"""
    rng = np.random.default_rng(seed)
    t = df.index
    mins = np.array(t.hour * 60 + t.minute)
    day = np.array(t.date)
    o, c = df["open"].to_numpy(), df["close"].to_numpy()
    cand = {}
    for i in np.flatnonzero((mins >= 7 * 60 + 30) & (mins < 9 * 60 + 30)):
        cand.setdefault(day[i], []).append(i)
    rows = []
    for _, tr in trades.iterrows():
        idxs = cand.get(tr["date"])
        if idxs:
            rows.append((np.array(idxs), int(tr["barras"])))
    means = np.empty(n_perm)
    for p in range(n_perm):
        x = []
        for idxs, dur in rows:
            j = int(rng.choice(idxs))
            k = min(j + dur, len(df) - 1)
            x.append(c[k] - o[j] if day[k] == day[j] else np.nan)
        means[p] = np.nanmean(x)
    real = float(trades["pts"].mean())
    return {"placebo_pts_promedio": round(float(means.mean()), 2), "p_valor": round(float((means >= real).mean()), 4)}


def stats(tr: pd.DataFrame) -> dict:
    if len(tr) < 5:
        return {"n": len(tr)}
    net = tr["pts"] - COST_PTS
    eq = (net * 50).cumsum()
    return {"n": len(tr), "pts_bruto": round(tr["pts"].mean(), 2), "pts_neto": round(net.mean(), 2),
            "t_neto": round(net.mean() / (net.std(ddof=1) / np.sqrt(len(net))), 2) if len(net) > 2 else np.nan,
            "aciertos_%": round(100 * (net > 0).mean(), 1), "total_usd_neto": round(net.sum() * 50, 0),
            "peor_caida_usd": round(float((eq - eq.cummax()).min()), 0), "salen_por_regla_%": round(100 * (tr["motivo"] == "regla").mean(), 1),
            "barras_promedio": round(tr["barras"].mean(), 1)}


if __name__ == "__main__":
    parts = [load_es_bars_csv(p) for p in sys.argv[1:]]
    bars = pd.concat(parts).sort_index()
    bars = bars[~bars.index.duplicated(keep="last")]
    print(f"Barras: {len(bars)}  ({bars.index[0]:%Y-%m-%d} a {bars.index[-1]:%Y-%m-%d})")
    df = add_manuel_indicators(bars)
    pd.set_option("display.width", 220)
    for mode, text in (("A", "MACD literal: histograma MENOR que la barra anterior"), ("B", "MACD alternativo: histograma MAYOR que la barra anterior (se acorta si es rojo)")):
        tr = run(df, signals(df, mode))
        print(f"\n===== Modo {mode}: {text} =====")
        print(pd.Series(stats(tr)).to_string())
        if len(tr) >= 20:
            print("Placebo (entrada al azar en la misma ventana, misma duración):", placebo(df, tr))
            yr = pd.to_datetime(tr["date"]).dt.year
            print("\nPor año:")
            print(pd.DataFrame({int(y): stats(g) for y, g in tr.groupby(yr)}).T.to_string())
    print("\nSe aprueba solo si el neto es positivo, t > 2, p < 0.008 contra el placebo y el signo se repite en la mayoría de los años.")
