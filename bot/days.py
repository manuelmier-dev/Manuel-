"""Arma la tabla de días para el backtest a partir del resumen de cadenas y las barras de ES."""
from datetime import time

import pandas as pd

NY = "America/New_York"


def build_days(summary: pd.DataFrame, es_bars: pd.DataFrame, snapshot: time = time(9, 20),
               bar_minutes: int = 5, max_gap_min: int = 30) -> tuple[pd.DataFrame, list[str]]:
    """Decisiones de Manuel: movimiento esperado = el de TradeStation (si falta, el straddle);
    walls = mayor Open Interest. Base = precio de ES a las 9:20 menos el SPX de ese momento.
    Las barras de ES deben incluir pre-mercado (al menos 9:00 a 9:30)."""
    rows, skipped = [], []
    for _, r in summary.iterrows():
        d = pd.Timestamp(r["date"])
        ts = pd.Timestamp.combine(d.date(), snapshot).tz_localize(NY)
        # solo barras ya cerradas a la hora del archivo (inicio + duración <= 9:20)
        done = es_bars.loc[: ts - pd.Timedelta(minutes=bar_minutes)]
        if done.empty or ts - done.index[-1] > pd.Timedelta(minutes=max_gap_min):
            skipped.append(f"{d.date()}: no hay barra de ES cerca de las {snapshot:%H:%M}")
            continue
        basis = float(done["close"].iloc[-1]) - float(r["spot"])
        if not -30 <= basis <= 150:
            skipped.append(f"{d.date()}: base ES-SPX de {basis:.0f} pts fuera de lo normal (¿precios ajustados o zona horaria?)")
            continue
        em = r["em_tradestation"] if pd.notna(r["em_tradestation"]) else r["em_straddle"]
        rows.append({
            "date": d.date(),
            "gex_bn": r["gex_bn"], "gex_ratio": r["gex_ratio"],
            "em_pts": float(em),
            "call_wall": r["call_wall_oi"], "put_wall": r["put_wall_oi"],
            "basis": basis,
            "oi_date": (d - pd.tseries.offsets.BDay(1)).date(),  # OI del día hábil anterior
        })
    out = pd.DataFrame(rows)
    if not out.empty:
        out = out.set_index("date")
    return out, skipped
