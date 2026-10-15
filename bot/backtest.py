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


def evaluate_signal(row, call_w, put_w, tol, p: Params):
    """Qué ve el bot en una barra: lado (corto en el call wall, largo en el put wall), cuántas confirmaciones y si cerró del lado de adentro."""
    near_call = bool(pd.notna(call_w) and row["high"] >= call_w - tol)
    near_put = bool(pd.notna(put_w) and row["low"] <= put_w + tol)
    side = "short" if (near_call and not near_put) else "long" if (near_put and not near_call) else None
    if side is None:
        return None
    rejected_ok = not ((side == "short" and row["close"] >= call_w) or (side == "long" and row["close"] <= put_w))
    return {"side": side, "conf": confirmations(row, side, p), "rejection_ok": rejected_ok}


def _levels(next_open, side, call_w, put_w, em, p: Params):
    d = 1 if side == "long" else -1
    entry = next_open + d * p.slippage_pts
    stop = entry - d * p.stop_frac * em
    opp = put_w if side == "short" else call_w
    raw_target = entry + d * p.target_frac * em
    if pd.isna(opp):
        target = raw_target
    else:
        target = max(raw_target, opp) if side == "short" else min(raw_target, opp)
    return entry, stop, target, d


def run_backtest(bars: pd.DataFrame, days: pd.DataFrame, p: Params = Params(), by_day: dict | None = None):
    """`by_day` (opcional): las barras con indicadores ya agrupadas por día; sirve para repetir el backtest muchas veces sin recalcular."""
    errs = validate_days(days) + (validate_bars(bars) if by_day is None else [])
    if errs:
        raise ValueError("Datos inválidos:\n- " + "\n- ".join(errs))

    if by_day is None:
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
        if len(b.between_time("09:30", "15:55")) < p.min_session_bars:
            skipped.append((date, "sesion_incompleta"))     # p. ej. el día de hoy, mientras sigue abierto el mercado
            continue
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
            sig = evaluate_signal(row, call_w, put_w, tol, p)
            if sig is None or sig["conf"] < p.confirmations_required or (p.require_rejection and not sig["rejection_ok"]):
                i += 1                      # sin señal, o la barra cerró del lado de afuera del wall (se rompió, no rebotó)
                continue
            side = sig["side"]
            nxt = b.iloc[i + 1]
            entry, stop, target, d = _levels(nxt["open"], side, call_w, put_w, em, p)
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
                "pts": pts, "usd": pts * p.point_value - p.commission_rt, "tipo": "normal",
            })
            if reason != "stop" or p.second_entry == "ninguna":
                break          # solo se reintenta después de un stop
            if p.second_entry == "reversa":
                # diagnóstico para días de ruptura: entrada inmediata en sentido contrario, sin confirmaciones
                if j + 1 < len(b) and entries < p.max_entries:
                    side2 = "short" if side == "long" else "long"
                    n2 = b.iloc[j + 1]
                    e2, s2, t2, d2 = _levels(n2["open"], side2, call_w, put_w, em, p)
                    if d2 * (t2 - e2) > 0:
                        k2, x2, r2 = _manage(b, j + 1, side2, e2, s2, t2, p)
                        entries += 1
                        trades.append({
                            "date": date, "n": entries, "side": side2, "entry_time": n2.name, "entry": e2, "stop": s2, "target": t2,
                            "exit_time": b.index[k2], "exit": x2, "reason": r2, "pts": d2 * (x2 - e2),
                            "usd": d2 * (x2 - e2) * p.point_value - p.commission_rt, "tipo": "reversa",
                        })
                break
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
