"""Uso:  python -m bot.run_trend "<carpeta de cadenas>" "<barras de ES .csv>" [salida.csv]

Prueba la ruptura del rango de la primera hora en los días de gamma negativo (diagnóstico, no una estrategia aprobada).
"""
import sys
from itertools import product
from pathlib import Path

import pandas as pd

from .backtest import summarize
from .days import build_days
from .journal import load_es_bars_csv
from .loaders import summarize_folder
from .trend import OrbParams, run_orb

if __name__ == "__main__":
    folder, bars_path = sys.argv[1], sys.argv[2]
    out = Path(sys.argv[3] if len(sys.argv) > 3 else "ruptura_tendencia.csv")
    summary, _ = summarize_folder(folder)
    bars = load_es_bars_csv(bars_path)
    days, skipped = build_days(summary, bars, wall_mode="oi_1em")
    n_trend = int((days["gex_bn"] <= 0).sum()) if len(days) else 0
    rows = []
    for stop_mode, target, buf in product(["mitad", "extremo"], [0.5, 1.0, 1.5], [0.0, 0.05]):
        t = run_orb(bars, days, o=OrbParams(stop_mode=stop_mode, target_em=target, buffer_frac=buf))
        rep = summarize(t, pd.DataFrame(columns=["date", "reason"]), n_trend)
        rows.append({"stop": stop_mode, "objetivo_EM": target, "colchon_EM": buf, "operaciones": rep.get("operaciones", 0),
                     "aciertos_%": rep.get("aciertos_%"), "resultado_total_usd": rep.get("resultado_total_usd"),
                     "peor_caida_usd": rep.get("peor_caida_usd"), "factor_ganancia": rep.get("factor_ganancia")})
    table = pd.DataFrame(rows)
    table.to_csv(out, index=False)
    pd.set_option("display.width", 200)
    print(f"Días de gamma negativo con barras: {n_trend}")
    print(table.to_string(index=False))
    print("\n*** Hipótesis en prueba. Con pocos días no concluye nada. ***")
