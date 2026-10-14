"""Estrategia candidata para días de TENDENCIA (gamma negativo): ruptura del rango de la primera hora (ORB). Solo para PROBAR.

Idea: en los días de gamma negativo no se opera la reversión a la media. Si el mercado rompe el rango de 9:30-10:30, se sigue la ruptura.
- Rango = máximo y mínimo de las barras de 9:30 a 10:25. Desde las 10:30, la primera barra que CIERRA fuera del rango (más un colchón)
  da la señal; la entrada es la apertura de la barra siguiente. Una entrada por día.
- Stop: la mitad del rango ("mitad") o el lado contrario ("extremo"), nunca menos de 0.2 EM ni más de 0.8 EM.
- Objetivo: `target_em` x EM. Cierre forzado a las 15:55.
Es una hipótesis: no hay evidencia todavía. Se prueba con la historia grande antes de pensar en operarla.
"""
from dataclasses import dataclass
from datetime import time

import pandas as pd

from .backtest import _manage
from .config import Params


@dataclass(frozen=True)
class OrbParams:
    range_start: time = time(9, 30)
    range_end: time = time(10, 30)
    buffer_frac: float = 0.05          # colchón sobre el rango, como fracción del EM
    stop_mode: str = "mitad"           # "mitad" o "extremo"
    target_em: float = 1.0
    min_stop_frac: float = 0.2
    max_stop_frac: float = 0.8
    entry_until: time = time(14, 0)


def run_orb(bars: pd.DataFrame, days: pd.DataFrame, p: Params = Params(), o: OrbParams = OrbParams()) -> pd.DataFrame:
    by_day = {d: g for d, g in bars.groupby(bars.index.date)}
    trades = []
    for key, day in days.iterrows():
        date = pd.Timestamp(key).date()
        if not day["gex_bn"] <= 0 or not day["em_pts"] >= p.min_expected_move_pts or date not in by_day:
            continue                                       # solo días de tendencia, con movimiento esperado suficiente
        b = by_day[date].between_time("09:30", "15:55")
        if len(b) < p.min_session_bars:
            continue
        em = float(day["em_pts"])
        rng = b[(b.index.time >= o.range_start) & (b.index.time < o.range_end)]
        if len(rng) < 10:
            continue
        hi, lo = float(rng["high"].max()), float(rng["low"].min())
        buf = o.buffer_frac * em
        after = b[(b.index.time >= o.range_end) & (b.index.time <= o.entry_until)]
        for i in range(len(after)):
            row = after.iloc[i]
            side = "long" if row["close"] > hi + buf else "short" if row["close"] < lo - buf else None
            if side is None:
                continue
            k = b.index.get_loc(after.index[i])
            if k + 1 >= len(b):
                break
            nxt = b.iloc[k + 1]
            d = 1 if side == "long" else -1
            entry = nxt["open"] + d * p.slippage_pts
            far = lo if side == "long" else hi
            mid = (hi + lo) / 2
            raw_stop = mid if o.stop_mode == "mitad" else far
            dist = min(max(abs(entry - raw_stop), o.min_stop_frac * em), o.max_stop_frac * em)
            stop = entry - d * dist
            target = entry + d * o.target_em * em
            j, exit_px, reason = _manage(b, k + 1, side, entry, stop, target, p)
            pts = d * (exit_px - entry)
            trades.append({"date": date, "n": 1, "side": side, "entry_time": nxt.name, "entry": entry, "stop": stop, "target": target,
                           "exit_time": b.index[j], "exit": exit_px, "reason": reason, "pts": pts,
                           "usd": pts * p.point_value - p.commission_rt, "tipo": "ORB", "rango_pts": hi - lo})
            break                                          # una entrada por día
    return pd.DataFrame(trades)
