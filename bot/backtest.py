"""Backtest de ES con las reglas de Manuel. Una barra a la vez, sin mirar el futuro.

Convenciones (SUPUESTOS, ver README):
- El EM es el straddle 0DTE en puntos; stop = stop_frac*EM, objetivo = target_frac*EM.
- Los walls son strikes de SPX; se pasan a ES sumando la base (ES - SPX) del día.
- La señal se evalúa al CIERRE de una barra; la entrada es la APERTURA de la siguiente.
- Si en una misma barra tocan stop y objetivo, se asume que primero fue el stop.
- La 2a entrada solo existe después de un stop y exige confirmaciones otra vez.
"""
from dataclasses import dataclass

import numpy as np
import pandas as pd

from .config import Params
from .indicators import add_indicators, confirmations
from .validate import validate_bars, validate_days


def skip_reason(day: pd.Series, p: Params) -> str | None:
    col = "gex_ratio" if p.gex_metric == "ratio" else "gex_bn"
    if not day[col] > p.gex_min:
        return "gamma_negativo_tendencia"
    if not day["em_pts"] >= p.min_expected_move_pts:
        return "movimiento_esperado_bajo"
    return None


def _manage(bars, start, side, entry, stop, target, p):
    """Devuelve (índice de salida, precio de salida, motivo)."""
    d = 1 if side == "long" else -1
    for j in range(start, len(bars)):
        r = bars.iloc[j]
        if side == "short":
            if r["high"] >= stop:
                return j, max(stop, r["open"]) + p.slippage_pts, "stop"
            if r["low"] <= target:
                return j, target + p.slippage_pts, "target"
        else:
            if r["low"] <= stop:
                return j, min(stop, r["open"]) - p.slippage_pts, "stop"
            if r["high"] >= target:
                return j, target - p.slippage_pts, "target"
        if r.name.time() >= p.flat_time:
            return j, r["open"] - d * p.slippage_pts, "cierre_dia"
    last = bars.iloc[-1]
    return len(bars) - 1, last["close"] - d * p.slippage_pts, "cierre_dia"


def run_backtest(bars: pd.DataFrame, days: pd.DataFrame, p: Params = Params()):
    errs = validate_bars(bars) + validate_days(days)
    if errs:
        raise ValueError("Datos inválidos:\n- " + "\n- ".join(errs))

    ind = add_indicators(bars, p)
    by_day = {d: g for d, g in ind.groupby(ind.index.date)}
    trades, skipped = [], []

    for key, day in days.iterrows():
        date = pd.Timestamp(key).date()
        why = skip_reason(day, p)
        if why:
            skipped.append((date, why))
            continue
        if date not in by_day:
            skipped.append((date, "sin_barras"))
            continue

        b = by_day[date]
        b = b[b.index.time >= p.entry_start]
        em = float(day["em_pts"])
        tol = p.zone_tol_frac * em
        call_w = day["call_wall"] + day["basis"]
        put_w = day["put_wall"] + day["basis"]

        entries, i, last_stop = 0, 0, False
        while i < len(b) - 1 and entries < p.max_entries:
            row = b.iloc[i]
            t = row.name.time()
            limit = p.entry_end if entries == 0 else p.reentry_end
            if t > limit:
                break
            near_call = row["high"] >= call_w - tol
            near_put = row["low"] <= put_w + tol
            side = None
            if near_call and not near_put:
                side = "short"
            elif near_put and not near_call:
                side = "long"
            if side is None or confirmations(row, side, p) < p.confirmations_required:
                i += 1
                continue

            nxt = b.iloc[i + 1]
            d = 1 if side == "long" else -1
            entry = nxt["open"] + d * p.slippage_pts
            stop = entry - d * p.stop_frac * em
            opp = put_w if side == "short" else call_w
            raw_target = entry + d * p.target_frac * em
            target = max(raw_target, opp) if side == "short" else min(raw_target, opp)
            if d * (target - entry) <= 0:
                i += 1
                continue

            j, exit_px, reason = _manage(b, i + 1, side, entry, stop, target, p)
            pts = d * (exit_px - entry)
            entries += 1
            trades.append({
                "date": date, "n": entries, "side": side,
                "entry_time": nxt.name, "entry": entry, "stop": stop, "target": target,
                "exit_time": b.index[j], "exit": exit_px, "reason": reason,
                "pts": pts, "usd": pts * p.point_value - p.commission_rt,
            })
            if reason != "stop":
                break          # solo se reintenta después de un stop
            i = j + 1

    return pd.DataFrame(trades), pd.DataFrame(skipped, columns=["date", "reason"])


def summarize(trades: pd.DataFrame, skipped: pd.DataFrame, n_days: int) -> dict:
    if trades.empty:
        return {"dias": n_days, "dias_sin_operar": len(skipped), "operaciones": 0}
    w = trades[trades["usd"] > 0]["usd"]
    l = trades[trades["usd"] <= 0]["usd"]
    eq = trades["usd"].cumsum()
    return {
        "dias": n_days,
        "dias_sin_operar": len(skipped),
        "operaciones": len(trades),
        "aciertos_%": round(100 * len(w) / len(trades), 1),
        "ganancia_media_usd": round(w.mean(), 2) if len(w) else 0.0,
        "perdida_media_usd": round(l.mean(), 2) if len(l) else 0.0,
        "factor_ganancia": round(w.sum() / abs(l.sum()), 2) if len(l) and l.sum() != 0 else None,
        "resultado_total_usd": round(trades["usd"].sum(), 2),
        "peor_caida_usd": round((eq - eq.cummax()).min(), 2),
        "segundas_entradas": int((trades["n"] == 2).sum()),
    }
