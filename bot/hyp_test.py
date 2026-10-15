"""Prueba de HIPÓTESIS PRE-REGISTRADAS de ES (reglas fijas, definidas antes de mirar los resultados), con años de datos.

Uso:  python -m bot.hyp_test "<carpeta de Theta>" "<barras de ES .csv>" [fecha_corte=2025-10-01]

Reglas (todas con 1 contrato, costo 0.58 pts = 29 USD por operación):
  M1  Momento hacia el cierre: señal = signo de (cierre 10:00 - apertura 9:30). Entra a las 15:30, sale a las 15:55 (cierre de la barra).
  M2  Igual, pero la señal incluye la noche: signo de (cierre 10:00 - cierre de ayer).
  M3  Igual, pero la señal es lo que hizo el precio de 15:00 a 15:30 (momento de la última media hora).
  G1  Hueco a favor: si |apertura - cierre de ayer| >= 0.25 EM, opera en el sentido del hueco de 9:30 a 11:00.
  G2  Hueco en contra: igual, en sentido contrario.
  N1  Noche: comprar al cierre (15:55) y vender a la apertura siguiente (9:30). Es "beta" del mercado: referencia, no una ventaja.
Para cada regla: promedio por operación, estadístico t, aciertos, resultado neto, entrenamiento vs comprobación, p-valor contra señales
mezcladas al azar, y diferencia entre días de gamma positivo y negativo (la idea: con gamma negativo el momento debería ser más fuerte).
Son 6 reglas: para llamar "hallazgo" a algo se exige p < 0.008 (0.05 / 6) Y que se repita en la comprobación.
"""
import sys

import numpy as np
import pandas as pd

from .config import Params
from .days import build_days
from .journal import load_es_bars_csv
from .loaders import summarize_folder

COST_PTS = (Params().commission_rt + 2 * Params().slippage_pts * Params().point_value) / Params().point_value      # 0.58


def _bar(g: pd.DataFrame, hhmm: str, col: str):
    ts = [t for t in g.index if t.strftime("%H:%M") == hhmm]
    return float(g.loc[ts[0], col]) if ts else np.nan


def day_features(bars: pd.DataFrame) -> pd.DataFrame:
    rows, prev_close, prev_date = [], np.nan, None
    by_day = {d: g for d, g in bars.groupby(bars.index.date)}
    dates = sorted(by_day)
    for i, d in enumerate(dates):
        g = by_day[d]
        rth = g.between_time("09:30", "15:55")
        if len(rth) < 70 or rth.index[0].strftime("%H:%M") != "09:30":
            continue
        close_day = _bar(g, "15:55", "close")
        nxt = by_day.get(dates[i + 1]) if i + 1 < len(dates) else None
        rows.append({"date": d, "open": _bar(g, "09:30", "open"), "c1000": _bar(g, "09:55", "close"), "o1100": _bar(g, "11:00", "open"),
                     "o1500": _bar(g, "15:00", "open"), "c1530": _bar(g, "15:25", "close"), "o1530": _bar(g, "15:30", "open"),
                     "close": close_day, "prev_close": prev_close,
                     "next_open": _bar(nxt, "09:30", "open") if nxt is not None else np.nan})
        prev_close = close_day
    return pd.DataFrame(rows).set_index("date")


def rule_returns(f: pd.DataFrame, em: pd.Series) -> pd.DataFrame:
    """Para cada regla: señal (+1/-1/0) y resultado bruto en puntos de ES."""
    late = f["close"] - f["o1530"]
    gap = f["open"] - f["prev_close"]
    big = gap.abs() >= 0.25 * em.reindex(f.index)
    g_sig = np.sign(gap).where(big, 0.0)
    out = pd.DataFrame(index=f.index)
    out["M1_sig"], out["M1_pts"] = np.sign(f["c1000"] - f["open"]), late
    out["M2_sig"], out["M2_pts"] = np.sign(f["c1000"] - f["prev_close"]), late
    out["M3_sig"], out["M3_pts"] = np.sign(f["c1530"] - f["o1500"]), late
    out["G1_sig"], out["G1_pts"] = g_sig, f["o1100"] - f["open"]
    out["G2_sig"], out["G2_pts"] = -g_sig, f["o1100"] - f["open"]
    out["N1_sig"], out["N1_pts"] = pd.Series(1.0, index=f.index), f["next_open"] - f["close"]
    return out


RULES = ["M1", "M2", "M3", "G1", "G2", "N1"]


def evaluate(r: pd.DataFrame, gex: pd.Series, cut: str, n_perm: int = 2000, seed: int = 5) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for name in RULES:
        k = pd.DataFrame({"s": r[f"{name}_sig"], "x": r[f"{name}_pts"], "g": gex.reindex(r.index)}).dropna()
        k = k[k["s"] != 0]
        if len(k) < 60:
            rows.append({"regla": name, "operaciones": len(k)})
            continue
        pnl = k["s"] * k["x"]
        net = pnl - COST_PTS
        if name == "N1":
            p_val = np.nan                                         # no hay señal que mezclar: es "beta"
        else:
            null = np.array([(rng.permutation(k["s"].to_numpy()) * k["x"].to_numpy()).mean() for _ in range(n_perm)])
            p_val = float((null >= pnl.mean()).mean())
        d = pd.to_datetime(pd.Series(k.index, index=k.index))
        tr, te = net[d < pd.Timestamp(cut)], net[d >= pd.Timestamp(cut)]
        neg, pos = pnl[k["g"] <= 0], pnl[k["g"] > 0]
        diff_p = np.nan
        if len(neg) > 30 and len(pos) > 30 and name != "N1":
            obs = neg.mean() - pos.mean()
            lab = (k["g"] <= 0).to_numpy()
            nulls = []
            for _ in range(n_perm):
                sh = rng.permutation(lab)
                nulls.append(pnl.to_numpy()[sh].mean() - pnl.to_numpy()[~sh].mean())
            diff_p = float((np.array(nulls) >= obs).mean())
        rows.append({"regla": name, "operaciones": len(k), "pts_bruto": round(pnl.mean(), 2), "pts_neto": round(net.mean(), 2),
                     "t_neto": round(net.mean() / (net.std(ddof=1) / np.sqrt(len(net))), 2), "aciertos_%": round(100 * (net > 0).mean(), 1),
                     "total_usd_neto": round(net.sum() * 50, 0), "neto_entrenamiento": round(tr.mean(), 2), "neto_comprobacion": round(te.mean(), 2),
                     "n_comprob": len(te), "p_azar": round(p_val, 4) if not np.isnan(p_val) else np.nan,
                     "pts_gamma_neg": round(neg.mean(), 2) if len(neg) else np.nan, "pts_gamma_pos": round(pos.mean(), 2) if len(pos) else np.nan,
                     "p_gamma_neg_mayor": round(diff_p, 4) if not np.isnan(diff_p) else np.nan})
    return pd.DataFrame(rows)


if __name__ == "__main__":
    folder, bars_path = sys.argv[1], sys.argv[2]
    cut = sys.argv[3] if len(sys.argv) > 3 else "2025-10-01"
    summary, _ = summarize_folder(folder)
    bars = load_es_bars_csv(bars_path)
    days, _ = build_days(summary, bars)
    f = day_features(bars)
    f = f[f.index.isin(days.index)]                          # solo días con Theta válido
    res = evaluate(rule_returns(f, days["em_pts"]), days["gex_bn"], cut)
    pd.set_option("display.width", 250)
    print(res.to_string(index=False))
    print(f"\nDías: {len(f)}. Costo supuesto {COST_PTS:.2f} pts por operación. Entrenamiento antes de {cut}; comprobación desde {cut}.")
    print("Hallazgo solo si p_azar < 0.008 Y neto_comprobacion > 0 con t > 2. N1 es el mercado subiendo (beta), no una ventaja.")
