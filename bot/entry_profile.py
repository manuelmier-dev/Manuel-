"""Perfil de la ENTRADA de don Manuel, sin ninguna regla de salida: ¿qué hace el precio DESPUÉS de entrar? (y se compara con entrar al azar)

Uso:  python -m bot.entry_profile <barras1.csv> [<barras2.csv> ...] [--instrumento ES|NQ|YM|RTY]

Para cada entrada (RSI < 33 y subiendo, cierre bajo la banda baja -2σ del VWAP Globex, barra alcista; ventana 7:30-10:30 NY; una por día) mide:
  - cuánto ganó o perdió a 5, 15, 30, 60, 120 y 240 minutos y al cierre (15:55), en puntos y contra entrar a una barra al azar de la misma ventana ese día;
  - la peor pérdida abierta (MAE) y la mejor ganancia abierta (MFE) hasta el cierre. Sirven para decidir UN stop y UN objetivo con datos, no con intuición.
Variantes: N (sin MACD) y B (MACD mayor). No se prueba ninguna salida aquí.
"""
import sys

import numpy as np
import pandas as pd

from .journal import load_es_bars_csv
from .strategy_m import WIN_END, WIN_START, _hm, add_manuel_indicators, costs, run, signals

HORIZONS = {"5 min": 1, "15 min": 3, "30 min": 6, "1 h": 12, "2 h": 24, "4 h": 48}


def forward_table(df: pd.DataFrame, idx: np.ndarray) -> pd.DataFrame:
    """Para cada barra de entrada (posición j): ganancia a cada horizonte (cierre de la barra j+k-1 menos apertura de j), al cierre, MAE y MFE."""
    t = df.index
    day = np.array(t.date)
    mins = np.array(t.hour * 60 + t.minute)
    o, c, h, l = (df[k].to_numpy() for k in ("open", "close", "high", "low"))
    rows = []
    for j in idx:
        end = j
        while end + 1 < len(df) and day[end + 1] == day[j] and mins[end] < 15 * 60 + 55:      # última barra del día (la de las 15:55)
            end += 1
        if mins[end] < 15 * 60 + 55:
            continue                                                                          # día incompleto
        row = {"j": j, "hora": t[j]}
        for name, k in HORIZONS.items():
            kk = min(j + k - 1, end)
            row[name] = c[kk] - o[j]
        row["cierre"] = c[end] - o[j]
        row["MAE"] = float(np.min(l[j:end + 1]) - o[j])
        row["MFE"] = float(np.max(h[j:end + 1]) - o[j])
        rows.append(row)
    return pd.DataFrame(rows)


def profile(df: pd.DataFrame, sig: pd.DataFrame, n_perm: int = 500, seed: int = 4) -> dict:
    tr = run(df, sig, exit_mode="X2")
    if len(tr) < 20:
        return {"n": len(tr)}
    idx = df.index.get_indexer(pd.DatetimeIndex(tr["entry_time"]))
    real = forward_table(df, idx)
    t = df.index
    day = np.array(t.date)
    mins = np.array(t.hour * 60 + t.minute)
    cand = {}
    for i in np.flatnonzero((mins >= _hm(WIN_START)) & (mins < _hm(WIN_END))):
        cand.setdefault(day[i], []).append(i)
    rng = np.random.default_rng(seed)
    days_real = [day[j] for j in real["j"]]
    cols = list(HORIZONS) + ["cierre"]
    null = np.empty((n_perm, len(cols)))
    for p in range(n_perm):
        picks = np.array([rng.choice(cand[d]) for d in days_real if d in cand])
        null[p] = forward_table(df, picks)[cols].mean().to_numpy()
    out = []
    for k, col in enumerate(cols):
        x = real[col]
        out.append({"horizonte": col, "promedio_pts": round(x.mean(), 2), "azar_pts": round(null[:, k].mean(), 2), "t": round(x.mean() / (x.std(ddof=1) / np.sqrt(len(x))), 2),
                    "p_vs_azar": round(float((null[:, k] >= x.mean()).mean()), 3), "%_positivo": round(100 * (x > 0).mean(), 1)})
    pre = real["hora"].map(lambda ts: ts.hour * 60 + ts.minute < 9 * 60 + 30)
    return {"n": len(real), "tabla": pd.DataFrame(out), "mae": real["MAE"].describe(percentiles=[.1, .25, .5, .75, .9]).round(1),
            "mfe": real["MFE"].describe(percentiles=[.1, .25, .5, .75, .9]).round(1),
            "premercado_vs_apertura": {"premercado": {"n": int(pre.sum()), "cierre_pts": round(real.loc[pre, "cierre"].mean(), 2) if pre.any() else np.nan},
                                       "apertura_9:30_a_10:30": {"n": int((~pre).sum()), "cierre_pts": round(real.loc[~pre, "cierre"].mean(), 2) if (~pre).any() else np.nan}}}


if __name__ == "__main__":
    instrument = sys.argv[sys.argv.index("--instrumento") + 1] if "--instrumento" in sys.argv else "ES"
    paths = [a for i, a in enumerate(sys.argv[1:], 1) if not a.startswith("--") and sys.argv[i - 1] != "--instrumento"]
    bars = pd.concat([load_es_bars_csv(p) for p in paths]).sort_index()
    bars = bars[~bars.index.duplicated(keep="last")]
    df = add_manuel_indicators(bars)
    pd.set_option("display.width", 200)
    cost_pts = costs(instrument)[0]
    print(f"Instrumento {instrument}; costo por operación {cost_pts:.2f} pts. Ganancias en puntos desde la apertura de la barra de entrada.")
    for mode, text in (("N", "SIN MACD"), ("B", "MACD mayor")):
        r = profile(df, signals(df, mode))
        print(f"\n===== Entrada {text}: {r['n']} operaciones =====")
        if "tabla" not in r:
            continue
        print(r["tabla"].to_string(index=False))
        print("\nPeor pérdida abierta (MAE, pts):", r["mae"].to_dict())
        print("Mejor ganancia abierta (MFE, pts):", r["mfe"].to_dict())
        print("Por hora de entrada:", r["premercado_vs_apertura"])
    print("\n'azar_pts' = lo que gana entrar a una barra al azar de la misma ventana el mismo día. La entrada tiene valor si 'promedio_pts' supera claramente al azar (p_vs_azar chico).")
