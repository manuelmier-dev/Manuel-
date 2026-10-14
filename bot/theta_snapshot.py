"""Resumen del día a partir de datos históricos de Theta Data (cotizaciones de las 9:20 y Open Interest).

Theta Data (plan Options Standard de Manuel, confirmado por su soporte el 14-oct-2026): opciones SPX desde 2016 a nivel de tick,
con cotizaciones, operaciones, OHLC, interés abierto, volatilidad implícita y griegas de PRIMER orden. La gamma es de segundo orden:
no viene incluida, por eso se calcula con bot.gex.gamma_from_quotes (validada contra archivos de TradeStation que sí la traen).
No ofrece ES ni precios intradía del índice SPX (el plan de índice es gratis: solo fin de día).

Contrato de entrada (lo que debe entregar el código que consulta la API; este módulo NO llama a Theta):
  quotes: strike, right ('C'/'P'), bid, ask  -> ÚLTIMA cotización anterior a las 9:20 NY del día, solo del vencimiento del día (0DTE)
  oi:     strike, right, open_interest        -> Open Interest que Theta publica la mañana del día (el cierre del día anterior)
Como en la cadena de TradeStation, a las 9:20 las cotizaciones son las del cierre previo: el "spot" por paridad es el cierre anterior.
"""
import pandas as pd

from .loaders import _summarize


def _side(df: pd.DataFrame, right: str, cols: list[str]) -> pd.DataFrame:
    x = df[df["right"].astype(str).str.upper().str[0] == right]
    return x.set_index("strike")[cols].add_suffix("_" + right.lower())


def summary_from_theta(trade_date: pd.Timestamp, quotes: pd.DataFrame, oi: pd.DataFrame, snapshot_et: str = "09:20") -> dict:
    q = quotes.copy()
    q["bid"] = pd.to_numeric(q["bid"], errors="coerce")
    q["ask"] = pd.to_numeric(q["ask"], errors="coerce")
    q = q[(q["ask"] > 0) & (q["bid"] >= 0) & (q["ask"] >= q["bid"])]          # fuera cotizaciones vacías o cruzadas
    z = (_side(q, "C", ["bid", "ask"]).join(_side(q, "P", ["bid", "ask"]), how="outer")
         .join(_side(oi, "C", ["open_interest"]), how="outer").join(_side(oi, "P", ["open_interest"]), how="outer"))
    z = z.rename(columns={"open_interest_c": "oi_c", "open_interest_p": "oi_p"}).reset_index()
    z[["oi_c", "oi_p"]] = z[["oi_c", "oi_p"]].fillna(0)
    z["mid_c"] = (z["bid_c"] + z["ask_c"]) / 2
    z["mid_p"] = (z["bid_p"] + z["ask_p"]) / 2
    z = z.sort_values("strike").reset_index(drop=True)
    if z.dropna(subset=["mid_c", "mid_p"]).empty:
        raise ValueError("Sin cotizaciones válidas de call y put en el mismo strike")
    out = _summarize(z, pd.Timestamp(trade_date), snapshot_et, float("nan"), "estimada")
    out["fuente"] = "theta"
    return out
