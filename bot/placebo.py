"""Backtest PLACEBO: la misma estrategia, con los walls cambiados por walls FALSOS, para saber si los walls aportan algo.

Uso:  python -m bot.placebo "<carpeta de Theta>" "<barras de ES .csv>" [repeticiones=40]

Un wall falso conserva la posición relativa típica (nivel - precio)/EM, pero de OTRO día (se mezclan entre días). Si la estrategia con walls reales
no gana más que con walls falsos, los walls no aportan nada: lo que se ve es el resto de la estrategia (VWAP, Bollinger, RSI, stops).
"""
import sys

import numpy as np
import pandas as pd

from .backtest import run_backtest
from .config import Params
from .days import build_days
from .indicators import add_indicators
from .journal import load_es_bars_csv
from .loaders import summarize_folder


def shuffle_walls(days: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """Cambia los walls de cada día por los de otro día, en posición relativa al precio (mismos pares call/put)."""
    em, c = days["em_pts"].to_numpy(), days["center_spx"].to_numpy()
    oc, op = (days["call_wall"].to_numpy() - c) / em, (days["put_wall"].to_numpy() - c) / em
    idx = rng.permutation(len(days))
    out = days.copy()
    out["call_wall"] = c + oc[idx] * em
    out["put_wall"] = c + op[idx] * em
    return out


def metrics(trades: pd.DataFrame) -> dict:
    if trades.empty:
        return {"operaciones": 0, "total_usd": 0.0, "usd_por_operacion": 0.0, "aciertos_%": np.nan, "factor_ganancia": np.nan}
    w, l = trades.loc[trades["usd"] > 0, "usd"], trades.loc[trades["usd"] <= 0, "usd"]
    return {"operaciones": len(trades), "total_usd": float(trades["usd"].sum()), "usd_por_operacion": float(trades["usd"].mean()),
            "aciertos_%": 100 * len(w) / len(trades), "factor_ganancia": float(w.sum() / abs(l.sum())) if len(l) and l.sum() else np.nan}


def placebo(days: pd.DataFrame, by_day: dict, bars: pd.DataFrame, n: int = 40, p: Params = Params(), seed: int = 11) -> dict:
    real, _ = run_backtest(bars, days, p, by_day=by_day)
    rng = np.random.default_rng(seed)
    runs = [metrics(run_backtest(bars, shuffle_walls(days, rng), p, by_day=by_day)[0]) for _ in range(n)]
    fake = pd.DataFrame(runs)
    m = metrics(real)
    out = {"real": m, "falsos_promedio": fake.mean().round(2).to_dict(),
           "p_valor_total_usd": round(float((fake["total_usd"] >= m["total_usd"]).mean()), 3),
           "p_valor_factor_ganancia": round(float((fake["factor_ganancia"].fillna(0) >= (m["factor_ganancia"] if pd.notna(m["factor_ganancia"]) else 0)).mean()), 3),
           "falsos_total_usd_min_max": (round(float(fake["total_usd"].min()), 0), round(float(fake["total_usd"].max()), 0)), "repeticiones": n}
    return out


if __name__ == "__main__":
    folder, bars_path = sys.argv[1], sys.argv[2]
    n = int(sys.argv[3]) if len(sys.argv) > 3 else 40
    summary, _ = summarize_folder(folder)
    bars = load_es_bars_csv(bars_path)
    days, _ = build_days(summary, bars, wall_mode="oi_1em")
    ind = add_indicators(bars, Params())
    by_day = {d: g for d, g in ind.groupby(ind.index.date)}
    for name, pp in (("TODAS las entradas (reglas de Manuel)", Params()), ("SOLO la primera entrada del día", Params(second_entry="ninguna"))):
        r = placebo(days, by_day, bars, n, pp)
        print(f"\n== {name}  ({n} repeticiones con walls falsos)")
        print("  con walls REALES :", {k: round(v, 2) for k, v in r["real"].items()})
        print("  con walls FALSOS :", r["falsos_promedio"], " rango del total:", r["falsos_total_usd_min_max"])
        print(f"  p-valor (¿los falsos igualan o superan a los reales?) total USD: {r['p_valor_total_usd']}   factor de ganancia: {r['p_valor_factor_ganancia']}")
    print("\np-valor chico (< 0.05) = los walls reales sí ayudan. p-valor grande = los walls no aportan nada.")
