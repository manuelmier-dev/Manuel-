"""Prueba corta de la API de Theta Terminal. Guarda las respuestas reales en ./theta_probe para ajustar el código.

Uso:  python -m bot.theta_probe [fecha_reciente=2026-10-13] [fecha_antigua=2022-06-01] [SPXW]
Las respuestas son datos de mercado (sin claves). Se pueden adjuntar al chat.
"""
import sys
from pathlib import Path

import pandas as pd

from .theta_client import BASE, build_url, fetch_text, ymd


def show(name, url, out):
    status, text = fetch_text(url)
    (out / f"{name}.txt").write_text(text, encoding="utf-8")
    lines = text.strip().splitlines()
    print(f"\n== {name}: HTTP {status}, {len(lines)} líneas, guardado en {out / (name + '.txt')}")
    for ln in lines[:4]:
        print("   ", ln[:200])
    return status, text


if __name__ == "__main__":
    recent = sys.argv[1] if len(sys.argv) > 1 else "2026-10-13"
    old = sys.argv[2] if len(sys.argv) > 2 else "2022-06-01"
    sym = sys.argv[3] if len(sys.argv) > 3 else "SPXW"
    out = Path("theta_probe")
    out.mkdir(exist_ok=True)
    print(f"Probando {BASE} con símbolo {sym}")
    st, _ = show("1_expiraciones", build_url("/option/list/expirations", {"symbol": sym}), out)
    if st != 200:
        print("\n*** No responde. ¿Está corriendo Theta Terminal v3? Revisa que escuche en el puerto 25503. ***")
        sys.exit(1)
    for tag, d in (("reciente", recent), ("antigua", old)):
        d8 = ymd(d)
        show(f"2_cotizacion_{tag}", build_url("/option/at_time/quote", {"symbol": sym, "expiration": d8, "strike": "*", "start_date": d8,
                                                                         "end_date": d8, "time_of_day": "09:20:00.000"}), out)
        show(f"3_open_interest_{tag}_date", build_url("/option/history/open_interest", {"symbol": sym, "expiration": d8, "strike": "*", "date": d8}), out)
        show(f"3_open_interest_{tag}_rango", build_url("/option/history/open_interest", {"symbol": sym, "expiration": d8, "strike": "*",
                                                                                         "start_date": d8, "end_date": d8}), out)
    print("\nListo. Adjunta en el chat los archivos de la carpeta theta_probe.")
