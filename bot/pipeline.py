"""De las cadenas y las barras de ES al resultado del backtest."""
import pandas as pd

from .backtest import run_backtest, summarize
from .config import Params
from .days import WALL_MODES, build_days


def backtest_from_summary(summary: pd.DataFrame, bars: pd.DataFrame, p: Params = Params(), wall_mode: str = "oi_1em"):
    days, skipped_days = build_days(summary, bars, wall_mode=wall_mode)
    if days.empty:
        return pd.DataFrame(), pd.DataFrame(columns=["date", "reason"]), days, skipped_days
    trades, skipped = run_backtest(bars, days, p)
    return trades, skipped, days, skipped_days


def report(trades: pd.DataFrame, skipped: pd.DataFrame, days: pd.DataFrame) -> dict:
    out = {"general": summarize(trades, skipped, len(days))}
    if not trades.empty:
        for n, t in trades.groupby("n"):
            out[f"entrada_{n}"] = summarize(t, skipped.iloc[0:0], t["date"].nunique())
        out["motivos_de_salida"] = trades["reason"].value_counts().to_dict()
    if not skipped.empty:
        out["dias_sin_operar_por"] = skipped["reason"].value_counts().to_dict()
    return out


def compare_wall_modes(summary: pd.DataFrame, bars: pd.DataFrame, p: Params = Params()) -> pd.DataFrame:
    """Corre el mismo backtest con cada definición de wall, para decidir con números."""
    rows = []
    for mode in WALL_MODES:
        trades, skipped, days, _ = backtest_from_summary(summary, bars, p, wall_mode=mode)
        rep = report(trades, skipped, days)["general"]
        rows.append({"wall": mode, "dias_con_wall_y_barras": len(days), **{k: rep.get(k) for k in (
            "dias_sin_operar", "operaciones", "aciertos_%", "ganancia_media_usd", "perdida_media_usd",
            "resultado_total_usd", "peor_caida_usd", "segundas_entradas")}})
    return pd.DataFrame(rows)


def sweep(summary: pd.DataFrame, bars: pd.DataFrame, base: Params = Params(), grid: dict | None = None) -> pd.DataFrame:
    """Mapa de sensibilidad: cómo cambia el resultado al variar parámetros. Es un DIAGNÓSTICO, no una búsqueda del mejor valor:
    con pocos días, el "mejor" de muchas combinaciones casi siempre es suerte."""
    from dataclasses import replace
    from datetime import time
    from itertools import product

    grid = grid or {
        "wall": list(WALL_MODES), "stop_frac": [0.2, 0.3, 0.4], "target_frac": [0.5, 0.9],
        "confirmations_required": [1, 2, 3], "entry_start": [time(9, 30), time(9, 35)],
    }
    keys = list(grid)
    days_cache: dict = {}
    rows = []
    for combo in product(*(grid[k] for k in keys)):
        cfg = dict(zip(keys, combo))
        mode = cfg.pop("wall", "oi_1em")
        if mode not in days_cache:
            days_cache[mode] = build_days(summary, bars, wall_mode=mode)[0]
        days = days_cache[mode]
        p = replace(base, **cfg)
        trades, skipped = run_backtest(bars, days, p) if not days.empty else (pd.DataFrame(), pd.DataFrame())
        rep = summarize(trades, skipped, len(days))
        rows.append({"wall": mode, **{k: (v.strftime("%H:%M") if hasattr(v, "strftime") else v) for k, v in cfg.items()},
                     "operaciones": rep.get("operaciones", 0), "aciertos_%": rep.get("aciertos_%"),
                     "resultado_total_usd": rep.get("resultado_total_usd"), "peor_caida_usd": rep.get("peor_caida_usd"),
                     "factor_ganancia": rep.get("factor_ganancia")})
    return pd.DataFrame(rows)
