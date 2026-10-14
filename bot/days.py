"""Arma la tabla de días para el backtest a partir del resumen de cadenas y las barras de ES.

Hallazgo (14-oct-2026): la cadena de las 9:20 trae precios de ANTES de abrir, así que el "spot" que sale por paridad es
el cierre del día anterior, no el precio de las 9:20. Por eso:
- la base ES - SPX se mide con el cierre de ES del día anterior (carry = ES_cierre_previo - spot_del_archivo), suavizada
  con la mediana de los últimos 5 días;
- el precio real de las 9:20 en coordenadas SPX es  ES(9:15) - carry;
- los walls "dentro de ±1 EM" se buscan alrededor de ese precio real, no del spot viejo.

Hallazgo (14-oct-2026, comparando 42 días): las cotizaciones de Theta a las 9:20 SÍ son del momento (NBBO en vivo; reflejan el
movimiento de la noche), a diferencia de las cadenas de TradeStation. En un día de Theta (fuente == "theta") el spot por paridad
ya es el precio real de las 9:20: la base ES - SPX es ES(9:15) - spot y el centro es el propio spot, sin usar el cierre previo.
"""
from datetime import time

import numpy as np
import pandas as pd

NY = "America/New_York"
CARRY_WINDOW = 5
CARRY_RANGE = (-30.0, 150.0)

WALL_MODES = {
    "oi": ("call_wall_oi", "put_wall_oi"),                  # mayor Open Interest de todo el archivo
    "oi_1em": ("call_wall_oi_1em", "put_wall_oi_1em"),      # mayor Open Interest dentro de ±1 EM del precio real
    "gex": ("call_wall_gex", "put_wall_gex"),               # mayor gamma
}


def _max_oi(table: pd.DataFrame, col: str, lo: float, hi: float) -> float:
    side = table[(table["strike"] >= lo) & (table["strike"] <= hi)].dropna(subset=[col])
    if side.empty or side[col].max() <= 0:
        return float("nan")
    return float(side.loc[side[col].idxmax(), "strike"])


def _prev_close(es_bars: pd.DataFrame, day_start: pd.Timestamp):
    """Cierre de la última barra de la sesión regular (15:55-16:00) anterior al día."""
    before = es_bars.loc[: day_start - pd.Timedelta(minutes=1)]
    last = before.between_time("15:55", "15:55")
    return None if last.empty else (last.index[-1], float(last["close"].iloc[-1]))


def build_days(summary: pd.DataFrame, es_bars: pd.DataFrame, snapshot: time = time(9, 20),
               bar_minutes: int = 5, max_gap_min: int = 30, wall_mode: str = "oi_1em") -> tuple[pd.DataFrame, list[str]]:
    """Decisiones de Manuel: movimiento esperado = el de TradeStation (si falta, el straddle); wall según `wall_mode`.
    Las barras de ES deben incluir el cierre del día anterior y el pre-mercado (al menos 9:00 a 9:30)."""
    rows, skipped, bases = [], [], []
    for _, r in summary.sort_values("date").iterrows():
        d = pd.Timestamp(r["date"])
        snap = pd.Timestamp(r["snapshot_et"]).time() if "snapshot_et" in r and r["snapshot_et"] else snapshot
        ts = pd.Timestamp.combine(d.date(), snap).tz_localize(NY)
        # solo barras ya cerradas a la hora del archivo (inicio + duración <= 9:20)
        done = es_bars.loc[: ts - pd.Timedelta(minutes=bar_minutes)]
        if done.empty or ts - done.index[-1] > pd.Timedelta(minutes=max_gap_min):
            skipped.append(f"{d.date()}: no hay barra de ES cerca de las {snap:%H:%M}")
            continue
        prev = _prev_close(es_bars, pd.Timestamp.combine(d.date(), time(9, 0)).tz_localize(NY))
        if prev is None:
            skipped.append(f"{d.date()}: no hay cierre de ES del día anterior")
            continue
        es_prev, es_now = prev[1], float(done["close"].iloc[-1])
        live = r.get("fuente") == "theta"                 # spot de las 9:20 en vivo (Theta) o del cierre previo (cadenas de TradeStation)
        bases.append((es_now if live else es_prev) - float(r["spot"]))
        carry = float(np.median(bases[-CARRY_WINDOW:]))
        if not CARRY_RANGE[0] <= carry <= CARRY_RANGE[1]:
            skipped.append(f"{d.date()}: base ES-SPX de {carry:.0f} pts fuera de lo normal (¿precios ajustados o zona horaria?)")
            continue
        center = float(r["spot"]) if live else es_now - carry   # precio real de las 9:20 en coordenadas SPX
        em = float(r["em_tradestation"] if pd.notna(r["em_tradestation"]) else r["em_proxy"])
        if wall_mode == "oi_1em" and isinstance(r.get("_table"), pd.DataFrame):
            t = r["_table"]
            cw = _max_oi(t, "oi_c", center, center + em)
            pw = _max_oi(t, "oi_p", center - em, center)
        else:
            cw, pw = (r[c] for c in WALL_MODES[wall_mode])
        if pd.isna(cw) and pd.isna(pw):
            skipped.append(f"{d.date()}: sin wall ({wall_mode})")
            continue
        rows.append({
            "date": d.date(),
            "gex_bn": r["gex_bn"], "gex_ratio": r["gex_ratio"],
            "em_pts": em, "call_wall": cw, "put_wall": pw,
            "basis": carry, "center_spx": center, "gap_nocturno": es_now - es_prev,
            "oi_date": (d - pd.tseries.offsets.BDay(1)).date(),  # OI del día hábil anterior
        })
    out = pd.DataFrame(rows)
    if not out.empty:
        out = out.set_index("date")
    return out, skipped
