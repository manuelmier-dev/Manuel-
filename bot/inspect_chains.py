"""Uso:  python -m bot.inspect_chains "/ruta/a/Cadenas SPX 0DTE"  [salida.csv]"""
import sys

import pandas as pd

from .loaders import summarize_folder

if __name__ == "__main__":
    folder = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else "resumen_cadenas.csv"
    df, errors = summarize_folder(folder)
    pd.set_option("display.width", 200, "display.max_columns", 30)
    if not df.empty:
        df.to_csv(out, index=False)
        print(df.drop(columns=["file", "strike_min", "strike_max", "call_wall_gex", "put_wall_gex", "snapshot_et"]).round(2).to_string(index=False))
        print(f"\nArchivos leídos: {len(df)}  |  guardado en {out}")
        print(f"GEX dentro de ±0.5 mil millones: {int((df['gex_bn'].abs() <= 0.5).sum())} días")
        print(f"GEX negativo: {int((df['gex_bn'] < 0).sum())} días")
        print(f"Proporción neto/total dentro de ±0.5: {int((df['gex_ratio'].abs() <= 0.5).sum())} días | mayor a 0.5: {int((df['gex_ratio'] > 0.5).sum())} días")
    for e in errors:
        print("ERROR:", e)
    if df.empty:
        print("No se pudo leer ningún archivo.")
