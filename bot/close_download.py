"""ETAPA 2 (descarga): cotizaciones reales de SPXW 0DTE a las 15:30, 15:45, 15:50, 15:55 y 15:59:59 de cada día.
Uso (en el servidor con Theta Terminal, SOLO cuando no corra otra descarga):
  python -m bot.close_download <carpeta_salida> <theta_resumen.csv> <desde> <hasta> [--max-min 600]
Salida: quotes/AAAA-MM-DD.csv  (t, strike, right, bid, ask, ask_size). Reanuda donde se quedó.
"""
import sys
import time
from pathlib import Path

import pandas as pd

from .theta_client import ThetaError, _col, _right, _strike, at_time_quote, fetch_text

TIMES = ["15:30:00.000", "15:45:00.000", "15:50:00.000", "15:55:00.000", "15:59:59.000"]


def normalize_snapshot(df: pd.DataFrame, t: str) -> pd.DataFrame:
    out = pd.DataFrame({"t": t[:8], "strike": _strike(df[_col(df, "strike")]), "right": _right(df[_col(df, "right")]),
                        "bid": pd.to_numeric(df[_col(df, "bid")], errors="coerce"), "ask": pd.to_numeric(df[_col(df, "ask")], errors="coerce")})
    sizes = [c for c in df.columns if c.lower() == "ask_size"]
    out["ask_size"] = pd.to_numeric(df[sizes[0]], errors="coerce") if sizes else float("nan")
    return out.dropna(subset=["strike"])


def day_quotes(day, fetch=fetch_text, symbol: str = "SPXW") -> pd.DataFrame:
    frames = []
    for t in TIMES:
        df = at_time_quote(symbol, day, day, t, fetch=fetch)
        if len(df):
            frames.append(normalize_snapshot(df, t))
    if not frames:
        raise ValueError("Theta no devolvió cotizaciones de cierre")
    return pd.concat(frames, ignore_index=True)


def run(out_dir, resumen_csv, start, end, max_min: float = 600, fetch=fetch_text, log=print) -> dict:
    res = pd.read_csv(resumen_csv, parse_dates=["date"]).drop_duplicates("date")
    res = res[(res["date"] >= pd.Timestamp(start)) & (res["date"] <= pd.Timestamp(end))].sort_values("date")
    out = Path(out_dir) / "quotes"
    out.mkdir(parents=True, exist_ok=True)
    t0, ok, bad, skip = time.time(), 0, 0, 0
    for d in res["date"]:
        f = out / f"{d.date()}.csv"
        if f.exists():
            skip += 1
            continue
        if (time.time() - t0) / 60 > max_min:
            log(f"Tiempo máximo ({max_min:.0f} min) alcanzado; vuelve a correr para seguir.")
            break
        t = time.time()
        try:
            day_quotes(d, fetch).to_csv(f, index=False)
            ok += 1
            log(f"{d.date()} ok en {time.time() - t:.0f}s")
        except (ThetaError, ValueError, KeyError) as e:
            bad += 1
            log(f"{d.date()} FALLÓ: {e}")
    log(f"Listo: {ok} nuevos, {skip} ya estaban, {bad} fallaron.")
    return {"ok": ok, "skip": skip, "bad": bad}


if __name__ == "__main__":
    a = [x for x in sys.argv[1:] if not x.startswith("--")]
    mm = float(sys.argv[sys.argv.index("--max-min") + 1]) if "--max-min" in sys.argv else 600
    if "--max-min" in sys.argv:
        a.remove(sys.argv[sys.argv.index("--max-min") + 1])
    run(a[0], a[1], a[2], a[3], mm)
