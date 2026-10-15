"""Hipótesis del HUECO (G2): ir EN CONTRA del hueco nocturno de ES de 9:30 a 11:00. Se prueba en una muestra NUEVA (años anteriores) además de la original.

Uso:  python -m bot.gap_study <barras1.csv> [<barras2.csv> ...]      (CSV de ts_bars o de ExportBarras5min; se pegan en orden)

Regla fijada ANTES de ver la muestra nueva (no hay datos de opciones antes de 2022, así que el "movimiento esperado" se aproxima con el rango
diario: EM ~ rango / 2.05, y 0.25 EM ~ 0.12 x el rango medio de los 20 días anteriores):
  hueco = apertura 9:30 - cierre de las 15:55 del día anterior.  Si |hueco| >= 0.12 x rango medio (20 días): opera EN CONTRA del hueco,
  entra a la apertura de las 9:30 y sale a la apertura de las 11:00. 1 contrato, sin stop, costo 0.58 pts (29 USD).
También se muestra G1 (a favor, es el espejo exacto) y la sensibilidad al umbral (0.06 / 0.12 / 0.25), sin elegir el mejor.
Se juzga igual que antes: p < 0.008 contra azar, t > 2 en lo neto y que se repita por periodos.
"""
import sys

import numpy as np
import pandas as pd

from .hyp_test import COST_PTS, _bar
from .journal import load_es_bars_csv

K_DEFAULT = 0.12


def daily_table(bars: pd.DataFrame) -> pd.DataFrame:
    rows, prev_close = [], np.nan
    for d, g in bars.groupby(bars.index.date):
        rth = g.between_time("09:30", "15:55")
        if len(rth) < 70 or rth.index[0].strftime("%H:%M") != "09:30":
            continue
        rows.append({"date": d, "open": _bar(g, "09:30", "open"), "o1100": _bar(g, "11:00", "open"), "close": _bar(g, "15:55", "close"),
                     "range": float(rth["high"].max() - rth["low"].min()), "prev_close": prev_close})
        prev_close = rows[-1]["close"]
    t = pd.DataFrame(rows).set_index("date")
    t["atr20"] = t["range"].shift(1).rolling(20).mean()                     # solo días anteriores
    return t


def gap_trades(t: pd.DataFrame, k: float = K_DEFAULT) -> pd.DataFrame:
    gap = t["open"] - t["prev_close"]
    trig = (gap.abs() >= k * t["atr20"]) & t["o1100"].notna()
    x = (t["o1100"] - t["open"])[trig]
    return pd.DataFrame({"gap": gap[trig], "x": x, "fade_pts": -np.sign(gap[trig]) * x})


def summarize_period(tr: pd.DataFrame, n_perm: int = 3000, seed: int = 3) -> dict:
    if len(tr) < 40:
        return {"n": len(tr)}
    rng = np.random.default_rng(seed)
    pnl = tr["fade_pts"]
    sig = -np.sign(tr["gap"]).to_numpy()
    null = np.array([(rng.permutation(sig) * tr["x"].to_numpy()).mean() for _ in range(n_perm)])
    net = pnl - COST_PTS
    return {"n": len(tr), "pts_bruto": round(pnl.mean(), 2), "pts_neto": round(net.mean(), 2), "t_neto": round(net.mean() / (net.std(ddof=1) / np.sqrt(len(net))), 2),
            "aciertos_%": round(100 * (net > 0).mean(), 1), "p_azar": round(float((null >= pnl.mean()).mean()), 4), "total_usd_neto": round(net.sum() * 50, 0)}


def report(bars: pd.DataFrame) -> dict:
    t = daily_table(bars)
    tr = gap_trades(t)
    idx = pd.to_datetime(pd.Series(tr.index, index=tr.index))
    out = {"todo": summarize_period(tr)}
    out["por_anio"] = {int(y): summarize_period(g, n_perm=1000) for y, g in tr.groupby(idx.dt.year)}
    out["sensibilidad_umbral"] = {k: summarize_period(gap_trades(t, k)) for k in (0.06, 0.12, 0.25)}
    return out


if __name__ == "__main__":
    parts = [load_es_bars_csv(p) for p in sys.argv[1:]]
    bars = pd.concat(parts).sort_index()
    bars = bars[~bars.index.duplicated(keep="last")]
    print(f"Barras: {len(bars)}  ({bars.index[0]:%Y-%m-%d} a {bars.index[-1]:%Y-%m-%d})")
    r = report(bars)
    pd.set_option("display.width", 220)
    print("\n== Todo (regla G2: contra el hueco, 9:30 a 11:00) ==")
    print(pd.Series(r["todo"]).to_string())
    print("\n== Por año ==")
    print(pd.DataFrame(r["por_anio"]).T.to_string())
    print("\n== Sensibilidad al umbral (k x rango medio 20 días) ==")
    print(pd.DataFrame(r["sensibilidad_umbral"]).T.to_string())
    print("\nSe aprueba solo si p_azar < 0.008, t_neto > 2 y el signo se repite en la mayoría de los años. 'G1' (a favor) es el espejo: mismo resultado con el signo contrario.")
