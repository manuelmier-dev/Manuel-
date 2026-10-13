"""VWAP (con bandas), Bollinger y RSI. Todos usan solo barras pasadas y la actual."""
from datetime import time

import numpy as np
import pandas as pd

from .config import Params


def rsi(close: pd.Series, period: int) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    out = 100 - 100 / (1 + rs)
    out = out.where(~((loss == 0) & (gain > 0)), 100.0)
    out = out.where(~((loss == 0) & (gain == 0)), 50.0)
    return out


def add_indicators(bars: pd.DataFrame, p: Params) -> pd.DataFrame:
    df = bars.copy()
    day = df.index.date
    tp = (df["high"] + df["low"] + df["close"]) / 3
    # el VWAP arranca a las 9:30 NY; las barras de pre-mercado no cuentan
    t = df.index.time
    rth = np.array([time(9, 30) <= x <= time(16, 0) for x in t])
    vol = df["volume"].where(rth, 0.0)
    g = pd.Series(day, index=df.index)
    cv = vol.groupby(g).cumsum().replace(0, np.nan)
    vwap = (tp * vol).groupby(g).cumsum() / cv
    var = ((tp**2) * vol).groupby(g).cumsum() / cv - vwap**2
    sd = np.sqrt(var.clip(lower=0))
    df["vwap"] = vwap
    df["vwap_up"] = vwap + p.vwap_band_std * sd
    df["vwap_dn"] = vwap - p.vwap_band_std * sd

    ma = df["close"].rolling(p.bb_period).mean()
    sdc = df["close"].rolling(p.bb_period).std(ddof=0)
    df["bb_up"] = ma + p.bb_std * sdc
    df["bb_dn"] = ma - p.bb_std * sdc
    df["rsi"] = rsi(df["close"], p.rsi_period)
    return df


def confirmations(row: pd.Series, side: str, p: Params) -> int:
    """Cuántas de las 3 referencias coinciden en que el precio está en un extremo."""
    c = row["close"]
    if side == "short":
        checks = [c >= row["bb_up"], c >= row["vwap_up"], row["rsi"] >= p.rsi_high]
    else:
        checks = [c <= row["bb_dn"], c <= row["vwap_dn"], row["rsi"] <= p.rsi_low]
    return int(sum(bool(x) for x in checks if not pd.isna(x)))
