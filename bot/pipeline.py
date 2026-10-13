"""De las cadenas y las barras de ES al resultado del backtest."""
import pandas as pd

from .backtest import run_backtest, summarize
from .config import Params
from .days import build_days


def backtest_from_summary(summary: pd.DataFrame, bars: pd.DataFrame, p: Params = Params()):
    days, skipped_days = build_days(summary, bars)
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
