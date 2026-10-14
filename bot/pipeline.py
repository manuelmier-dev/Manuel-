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
