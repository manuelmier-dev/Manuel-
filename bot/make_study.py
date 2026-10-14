"""Uso:  python -m bot.make_study "<carpeta de cadenas>" "<barras de ES .csv>" "<carpeta de salida>"

Genera estudio_dias.pdf (una página por día), png/AAAA-MM-DD.png y estudio_zonas.csv.
"""
import sys

from .journal import load_es_bars_csv
from .loaders import summarize_folder
from .study import make_study, summarize_zones

if __name__ == "__main__":
    folder, bars_path, out = sys.argv[1], sys.argv[2], sys.argv[3]
    summary, _ = summarize_folder(folder)
    table = make_study(summary, load_es_bars_csv(bars_path), out)
    print("\n".join(summarize_zones(table)))
    print(f"\nPDF: {out}/estudio_dias.pdf  |  imágenes: {out}/png  |  tabla: {out}/estudio_zonas.csv")
