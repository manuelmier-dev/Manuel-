"""Mapa de sensibilidad con DIVISIÓN entrenamiento / comprobación (nada de elegir la mejor combinación mirando todos los datos).

Uso:  python -m bot.sweep_split "<carpeta de Theta>" "<barras de ES .csv>" [fecha_corte=2025-10-01]

Corre cada combinación UNA vez sobre todos los días y reparte las operaciones por fecha: antes del corte = entrenamiento, desde el corte =
comprobación. La pregunta no es "cuál combinación gana" sino: ¿las que ganan en el entrenamiento también ganan en la comprobación?
Si no (correlación ~0), no hay nada que aprender de esos parámetros: era suerte.
"""
import sys
from dataclasses import replace
from itertools import product

import numpy as np
import pandas as pd

from .backtest import run_backtest
from .config import Params
from .days import build_days
from .indicators import add_indicators
from .journal import load_es_bars_csv
from .loaders import summarize_folder

MIN_TRADES = 40
GRID = {"stop_frac": [0.2, 0.5, 1.0], "target_frac": [0.9, 1.5], "confirmations_required": [1, 2],
        "second_entry": ["mismo_lado", "ninguna"], "require_rejection": [False, True]}


def period_metrics(trades: pd.DataFrame) -> dict:
    if len(trades) < MIN_TRADES:
        return {"n": len(trades), "usd_op": np.nan, "pf": np.nan, "aciertos": np.nan}
    w, l = trades.loc[trades["usd"] > 0, "usd"], trades.loc[trades["usd"] <= 0, "usd"]
    return {"n": len(trades), "usd_op": float(trades["usd"].mean()), "pf": float(w.sum() / abs(l.sum())) if len(l) and l.sum() else np.nan,
            "aciertos": 100 * len(w) / len(trades)}


def split_sweep(days: pd.DataFrame, by_day: dict, bars: pd.DataFrame, cut: str, grid: dict = GRID, base: Params = Params()) -> pd.DataFrame:
    keys = list(grid)
    rows = []
    for combo in product(*(grid[k] for k in keys)):
        cfg = dict(zip(keys, combo))
        trades, _ = run_backtest(bars, days, replace(base, **cfg), by_day=by_day)
        d = pd.to_datetime(trades["date"]) if len(trades) else pd.Series(dtype="datetime64[ns]")
        tr, te = trades[d < pd.Timestamp(cut)] if len(trades) else trades, trades[d >= pd.Timestamp(cut)] if len(trades) else trades
        a, b = period_metrics(tr), period_metrics(te)
        rows.append({**cfg, "n_train": a["n"], "usd_op_train": a["usd_op"], "pf_train": a["pf"], "n_test": b["n"], "usd_op_test": b["usd_op"],
                     "pf_test": b["pf"], "aciertos_test": b["aciertos"]})
    return pd.DataFrame(rows)


def summarize_split(res: pd.DataFrame) -> list[str]:
    ok = res.dropna(subset=["usd_op_train", "usd_op_test"])
    lines = [f"Combinaciones: {len(res)}; con operaciones suficientes en ambos periodos: {len(ok)}"]
    if len(ok) < 5:
        return lines + ["Muy pocas para concluir."]
    rho = ok["usd_op_train"].rank().corr(ok["usd_op_test"].rank())
    top = ok.sort_values("usd_op_train", ascending=False).head(max(3, len(ok) // 5))
    lines += [f"Correlación de orden entrenamiento vs comprobación (USD por operación): {rho:.2f}   (cerca de 0 = no se repite; cerca de 1 = sí)",
              f"Ganan (USD/operación > 0) en entrenamiento: {int((ok['usd_op_train'] > 0).sum())} de {len(ok)}; en comprobación: {int((ok['usd_op_test'] > 0).sum())} de {len(ok)}",
              f"El 20% MEJOR en entrenamiento ({len(top)} combinaciones): USD/operación entrenamiento {top['usd_op_train'].mean():+.1f} -> comprobación {top['usd_op_test'].mean():+.1f}"]
    return lines


if __name__ == "__main__":
    folder, bars_path = sys.argv[1], sys.argv[2]
    cut = sys.argv[3] if len(sys.argv) > 3 else "2025-10-01"
    summary, _ = summarize_folder(folder)
    bars = load_es_bars_csv(bars_path)
    days, _ = build_days(summary, bars, wall_mode="oi_1em")
    ind = add_indicators(bars, Params())
    by_day = {d: g for d, g in ind.groupby(ind.index.date)}
    res = split_sweep(days, by_day, bars, cut)
    res.to_csv("sweep_split.csv", index=False)
    pd.set_option("display.width", 220)
    print(res.sort_values("usd_op_train", ascending=False).round(2).to_string(index=False))
    print("\n" + "\n".join(summarize_split(res)))
    print(f"\nEntrenamiento: antes de {cut}. Comprobación: desde {cut}. Mínimo {MIN_TRADES} operaciones por periodo. Diagnóstico, no una receta.")
