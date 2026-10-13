"""Uso:  python -m bot.run_backtest "<carpeta de cadenas>" "<barras de ES .csv>" [operaciones.csv]

Con pocos días el resultado NO concluye nada: sirve para encontrar errores y ver el comportamiento.
"""
import json
import sys

from .journal import load_es_bars_csv
from .loaders import summarize_folder
from .pipeline import backtest_from_summary, report

if __name__ == "__main__":
    folder, bars_path = sys.argv[1], sys.argv[2]
    out = sys.argv[3] if len(sys.argv) > 3 else "operaciones.csv"
    summary, errors = summarize_folder(folder)
    bars = load_es_bars_csv(bars_path)
    trades, skipped, days, skipped_days = backtest_from_summary(summary, bars)
    print(json.dumps(report(trades, skipped, days), indent=2, ensure_ascii=False, default=str))
    if not trades.empty:
        trades.to_csv(out, index=False)
        print(f"Operaciones guardadas en {out}")
    for s in skipped_days + errors:
        print("AVISO:", s)
    print("\n*** Con pocos días, esto no concluye nada sobre la estrategia. ***")
