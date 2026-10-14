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


# --- Gamma calculada a partir de precios (para archivos sin columna de gamma, como los de agosto) ---
_erf = np.vectorize(__import__("math").erf)


def _ncdf(x):
    return 0.5 * (1.0 + _erf(np.asarray(x, dtype=float) / np.sqrt(2.0)))


def _bs_call(spot, strike, s):
    """Call de Black-Scholes con tasa 0; s = volatilidad * raíz(tiempo)."""
    d1 = (np.log(spot / strike) + 0.5 * s * s) / s
    return spot * _ncdf(d1) - strike * _ncdf(d1 - s)


def gamma_from_quotes(strikes, call_mid, put_mid, spot, min_price=0.05):
    """Gamma por strike a partir de los precios medios. Usa el lado fuera del dinero (el más líquido).

    Devuelve una Serie con la gamma por strike (NaN donde no hay precio confiable).
    Solo se usa si el archivo no trae gamma; se valida contra archivos que sí la traen.
    """
    k = np.asarray(strikes, dtype=float)
    otm_call = k >= spot
    price = np.where(otm_call, np.asarray(call_mid, dtype=float), np.asarray(put_mid, dtype=float))
    call_equiv = np.where(otm_call, price, price + spot - k)         # paridad: call = put + S - K
    ok = np.isfinite(price) & (price >= min_price)
    lo, hi = np.full(k.shape, 1e-4), np.full(k.shape, 0.25)
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        too_low = _bs_call(spot, k, mid) < call_equiv
        lo = np.where(too_low, mid, lo)
        hi = np.where(too_low, hi, mid)
    s = 0.5 * (lo + hi)
    d1 = (np.log(spot / k) + 0.5 * s * s) / s
    g = np.exp(-0.5 * d1 * d1) / np.sqrt(2 * np.pi) / (spot * s)
    return pd.Series(np.where(ok, g, np.nan), index=pd.Index(k, name="strike"))
