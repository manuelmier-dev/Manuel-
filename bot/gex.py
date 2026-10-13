"""Gamma exposure (GEX), walls y movimiento esperado a partir de la cadena SPX 0DTE."""
import numpy as np
import pandas as pd


def gamma_exposure(chain: pd.DataFrame, spot: float) -> dict:
    """chain: columnas strike, right ('C'/'P'), gamma, open_interest.

    Supuesto estándar (aproximación): los market makers están largos en calls y
    cortos en puts. GEX por strike = gamma * OI * 100 * spot^2 * 0.01
    (dólares de delta por cada 1% de movimiento). Calls suman, puts restan.
    """
    c = chain.copy()
    is_call = c["right"].str.upper().str[0] == "C"
    raw = c["gamma"] * c["open_interest"] * 100.0 * spot**2 * 0.01
    c["gex"] = np.where(is_call, raw, -raw)

    calls = c[is_call].groupby("strike")["gex"].sum()
    puts = c[~is_call].groupby("strike")["gex"].sum()
    net = c.groupby("strike")["gex"].sum()
    return {
        "total_bn": float(net.sum()) / 1e9,
        "gross_bn": float(c["gex"].abs().sum()) / 1e9,
        "call_wall": float(calls.idxmax()) if len(calls) else float("nan"),
        "put_wall": float(puts.idxmin()) if len(puts) else float("nan"),
        "per_strike": net,
    }


def expected_move(quotes: pd.DataFrame, spot: float) -> float:
    """Straddle ATM 0DTE en puntos. quotes: strike, right, mid."""
    strikes = quotes["strike"].unique()
    atm = strikes[np.argmin(np.abs(strikes - spot))]
    q = quotes[quotes["strike"] == atm]
    call = q[q["right"].str.upper().str[0] == "C"]["mid"]
    put = q[q["right"].str.upper().str[0] == "P"]["mid"]
    if call.empty or put.empty:
        raise ValueError(f"Falta call o put en el strike ATM {atm}")
    return float(call.iloc[0] + put.iloc[0])
