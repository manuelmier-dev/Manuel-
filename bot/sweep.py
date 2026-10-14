"""Uso:  python -m bot.sweep "<carpeta de cadenas>" "<barras de ES .csv>" [sensibilidad.csv]

Mapa de sensibilidad (diagnóstico). NO elegir la combinación "ganadora": con pocos días, la mejor de muchas es suerte.
"""
import sys

import pandas as pd

from .journal import load_es_bars_csv
from .loaders import summarize_folder
from .pipeline import sweep

if __name__ == "__main__":
    folder, bars_path = sys.argv[1], sys.argv[2]
    out = sys.argv[3] if len(sys.argv) > 3 else "sensibilidad.csv"
    summary, _ = summarize_folder(folder)
    table = sweep(summary, load_es_bars_csv(bars_path))
    table.to_csv(out, index=False)
    pd.set_option("display.width", 200)
    print(f"{len(table)} combinaciones guardadas en {out}")
    for col in ["wall", "stop_frac", "target_frac", "confirmations_required", "entry_start", "require_rejection"]:
        agg = table.groupby(col).agg(operaciones=("operaciones", "mean"), resultado_medio=("resultado_total_usd", "mean"),
                                     peor_caida_media=("peor_caida_usd", "mean"), combinaciones_con_ganancia=("resultado_total_usd", lambda s: int((s > 0).sum())))
        print(f"\nPromedio por {col}:\n", agg.round(0).to_string())
    print("\n*** Diagnóstico, no una búsqueda del mejor valor: con pocos días, la mejor combinación es casi siempre suerte. ***")
