"""Uso:  python -m bot.make_journal "<carpeta de cadenas>" [barras_es.csv] [bitacora.csv]

Sin barras de ES (omite el argumento o pon "-") solo llena la parte de antes de la apertura. Se puede volver a correr cuando lleguen las barras.
"""
import sys

import pandas as pd

from .journal import build_journal, first_hour_stats, load_es_bars_csv, regime_report
from .loaders import summarize_folder

if __name__ == "__main__":
    folder = sys.argv[1]
    bars = load_es_bars_csv(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2] not in ("", "-") else None
    out = sys.argv[3] if len(sys.argv) > 3 else "bitacora.csv"
    summary, errors = summarize_folder(folder)
    j = build_journal(summary, bars)
    j.to_csv(out, index=False)
    pd.set_option("display.width", 220, "display.max_columns", 40)
    print(f"Bitácora de {len(j)} días guardada en {out}")
    print(j["regime"].value_counts().to_string())
    if bars is not None:
        print("\nMáximo/mínimo entre 9:30 y 10:30:", first_hour_stats(j))
        print("\nPor régimen:\n", regime_report(j).to_string())
    for e in errors:
        print("ERROR:", e)
