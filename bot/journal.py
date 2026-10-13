"""Bitácora diaria: una fila por día, opere o no. Sirve para estudiar los días de tendencia después.

Parte 1 (antes de las 9:30): gamma, movimiento esperado, walls, régimen y si el bot operaría.
Parte 2 (después del cierre, si hay barras de ES): cuánto se movió el mercado y cuándo hizo máximo y mínimo.
Solo anota; no manda órdenes.
"""
from datetime import time

import numpy as np
import pandas as pd

from .backtest import skip_reason
from .config import Params

NY = "America/New_York"
SESSION_START, SESSION_END = time(9, 30), time(15, 55)   # inicio de la primera y de la última barra de 5 min
WINDOW_END = time(10, 30)
MIN_BARS = 70                                            # una sesión completa trae 78 barras de 5 min

POST_COLS = ["es_open", "es_high", "es_low", "es_close", "range_pts", "range_em", "close_open_pts",
             "move_em", "close_pos", "high_time", "low_time", "high_in_window", "low_in_window"]


def load_es_bars_csv(path) -> pd.DataFrame:
    """CSV con el tiempo en la primera columna y open, high, low, close, volume (el de export_es_bars.py)."""
    df = pd.read_csv(path, index_col=0)
    df.index = pd.to_datetime(df.index, utc=True).tz_convert(NY)
    return df.sort_index()


def _post_close(bars: pd.DataFrame, d, em: float) -> dict:
    day = bars.loc[str(d)] if str(d) in bars.index.strftime("%Y-%m-%d") else bars.iloc[0:0]
    s = day.between_time(SESSION_START, SESSION_END)
    if len(s) < MIN_BARS or s.index[0].time() != SESSION_START:
        return {c: np.nan for c in POST_COLS}
    hi, lo = float(s["high"].max()), float(s["low"].min())
    o, c = float(s["open"].iloc[0]), float(s["close"].iloc[-1])
    th, tl = s["high"].idxmax().time(), s["low"].idxmin().time()
    rng = hi - lo
    return {
        "es_open": o, "es_high": hi, "es_low": lo, "es_close": c,
        "range_pts": rng, "range_em": rng / em, "close_open_pts": c - o, "move_em": (c - o) / em,
        "close_pos": (c - lo) / rng if rng else np.nan,          # 0 = cerró en el mínimo, 1 = en el máximo
        "high_time": th, "low_time": tl,
        "high_in_window": SESSION_START <= th < WINDOW_END, "low_in_window": SESSION_START <= tl < WINDOW_END,
    }


def build_journal(summary: pd.DataFrame, es_bars: pd.DataFrame | None = None, p: Params = Params()) -> pd.DataFrame:
    rows = []
    for _, r in summary.iterrows():
        em = r["em_tradestation"] if pd.notna(r["em_tradestation"]) else r["em_straddle"]
        day = pd.Series({"gex_bn": r["gex_bn"], "gex_ratio": r["gex_ratio"], "em_pts": float(em)})
        why = skip_reason(day, p)
        row = {
            "date": pd.Timestamp(r["date"]).date(), "regime": "reversion" if r["gex_bn"] > 0 else "tendencia",
            "spot": r["spot"], "gex_bn": r["gex_bn"], "gex_ratio": r["gex_ratio"], "em_pts": float(em),
            "call_wall_oi": r["call_wall_oi"], "put_wall_oi": r["put_wall_oi"],
            "bot_opera": why is None, "motivo_no_opera": why or "",
        }
        row.update(_post_close(es_bars, pd.Timestamp(r["date"]).date(), float(em)) if es_bars is not None
                   else {c: np.nan for c in POST_COLS})
        rows.append(row)
    return pd.DataFrame(rows)


def first_hour_stats(j: pd.DataFrame) -> dict:
    """Prueba la observación de Manuel: ¿el máximo o el mínimo del día se hace entre 9:30 y 10:30?"""
    k = j.dropna(subset=["range_pts"])
    if k.empty:
        return {"dias_con_barras": 0}
    h, l = k["high_in_window"].astype(bool), k["low_in_window"].astype(bool)
    pct = lambda s: round(float(100 * s.mean()), 1)  # noqa: E731
    return {"dias_con_barras": len(k), "maximo_en_ventana_%": pct(h), "minimo_en_ventana_%": pct(l),
            "alguno_de_los_dos_%": pct(h | l), "ambos_%": pct(h & l)}


def regime_report(j: pd.DataFrame) -> pd.DataFrame:
    """¿Se comportan distinto los días de gamma positivo y negativo? (muestra chica: leer con cuidado)"""
    k = j.dropna(subset=["range_pts"]).copy()
    if k.empty:
        return pd.DataFrame()
    k["cierra_en_extremo"] = (k["close_pos"] >= 0.8) | (k["close_pos"] <= 0.2)
    k["alguno_ventana"] = k["high_in_window"].astype(bool) | k["low_in_window"].astype(bool)
    k["move_abs_em"] = k["move_em"].abs()
    return k.groupby("regime").agg(
        dias=("date", "count"), rango_sobre_em=("range_em", "mean"), movimiento_sobre_em=("move_abs_em", "mean"),
        cierra_en_extremo_pct=("cierra_en_extremo", lambda s: round(100 * s.mean(), 1)),
        extremo_en_ventana_pct=("alguno_ventana", lambda s: round(100 * s.mean(), 1))).round(2)
