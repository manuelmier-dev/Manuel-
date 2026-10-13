"""Lee las cadenas SPX 0DTE exportadas de TradeStation (.xls) y calcula el resumen del día.

El archivo se exporta antes de la apertura (9:20 NY), así que el Open Interest que trae
es el del día anterior: no hay información del futuro.
"""
import re
from pathlib import Path

import numpy as np
import pandas as pd

from .gex import expected_move, gamma_exposure

# columnas del archivo (posición): calls a la izquierda, strike al centro, puts a la derecha
C = dict(symbol=1, gamma=2, iv=3, oi=5, bid=7, ask=8)
STRIKE = 9
P = dict(bid=10, ask=11, oi=13, iv=14, gamma=16)


def _num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s.astype(str).str.replace(",", "").str.replace("%", "").str.strip(), errors="coerce")


def date_from_filename(path) -> pd.Timestamp:
    m = re.search(r"(\d{2})-(\d{2})-(\d{4})", Path(path).name)
    if not m:
        raise ValueError(f"No encuentro la fecha (dd-mm-aaaa) en el nombre: {Path(path).name}")
    return pd.Timestamp(year=int(m[3]), month=int(m[2]), day=int(m[1]))


def parse_chain_frame(raw: pd.DataFrame, trade_date: pd.Timestamp) -> dict:
    """raw: la hoja leída sin encabezados. Devuelve el resumen del día para el vencimiento 0DTE."""
    rows = raw[raw[C["symbol"]].astype(str).str.startswith("SPXW")].copy()
    if rows.empty:
        raise ValueError("No hay filas SPXW en el archivo")
    rows["exp"] = rows[C["symbol"]].str.extract(r"SPXW (\d{6})")[0]
    expected_exp = trade_date.strftime("%y%m%d")
    rows = rows[rows["exp"] == expected_exp]
    if rows.empty:
        raise ValueError(f"El archivo no trae el vencimiento 0DTE {expected_exp}")

    z = pd.DataFrame({
        "strike": _num(rows[STRIKE]),
        "g_c": _num(rows[C["gamma"]]), "oi_c": _num(rows[C["oi"]]),
        "bid_c": _num(rows[C["bid"]]), "ask_c": _num(rows[C["ask"]]),
        "g_p": _num(rows[P["gamma"]]), "oi_p": _num(rows[P["oi"]]),
        "bid_p": _num(rows[P["bid"]]), "ask_p": _num(rows[P["ask"]]),
    }).reset_index(drop=True)
    z["mid_c"] = (z["bid_c"] + z["ask_c"]) / 2
    z["mid_p"] = (z["bid_p"] + z["ask_p"]) / 2

    # precio del SPX por paridad put-call (el archivo no trae el precio del índice)
    ok = z.dropna(subset=["mid_c", "mid_p"])
    near = ok.iloc[(ok["mid_c"] - ok["mid_p"]).abs().argsort()[:5]]
    spot = float((near["strike"] + near["mid_c"] - near["mid_p"]).median())

    chain = pd.concat([
        pd.DataFrame({"strike": z["strike"], "right": "C", "gamma": z["g_c"], "open_interest": z["oi_c"]}),
        pd.DataFrame({"strike": z["strike"], "right": "P", "gamma": z["g_p"], "open_interest": z["oi_p"]}),
    ]).dropna()
    quotes = pd.concat([
        pd.DataFrame({"strike": z["strike"], "right": "C", "mid": z["mid_c"]}),
        pd.DataFrame({"strike": z["strike"], "right": "P", "mid": z["mid_p"]}),
    ]).dropna()
    g = gamma_exposure(chain, spot)

    # el encabezado de TradeStation trae su propio movimiento esperado: "(Custom=(±22.83))"
    head = " ".join(raw[0].dropna().astype(str))
    m = re.search(r"Custom=\(±([\d.]+)\)", head)

    return {
        "date": trade_date.date(),
        "spot": spot,
        "em_straddle": expected_move(quotes, spot),
        "em_tradestation": float(m[1]) if m else float("nan"),
        "gex_bn": g["total_bn"],
        "call_wall_gex": g["call_wall"],
        "put_wall_gex": g["put_wall"],
        "call_wall_oi": float(z.loc[z["oi_c"].idxmax(), "strike"]),
        "put_wall_oi": float(z.loc[z["oi_p"].idxmax(), "strike"]),
        "strike_min": float(z["strike"].min()),
        "strike_max": float(z["strike"].max()),
        "n_strikes": int(len(z)),
    }


def load_chain_file(path) -> dict:
    raw = pd.read_excel(path, header=None, engine="xlrd")
    out = parse_chain_frame(raw, date_from_filename(path))
    out["file"] = Path(path).name
    return out


def summarize_folder(folder, pattern="**/*.xls") -> tuple[pd.DataFrame, list[str]]:
    """Resume todos los archivos; los que fallan se reportan, no se ocultan."""
    rows, errors = [], []
    for f in sorted(Path(folder).glob(pattern)):
        try:
            rows.append(load_chain_file(f))
        except Exception as e:  # noqa: BLE001 - se reporta el archivo y el motivo
            errors.append(f"{f.name}: {e}")
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values("date").reset_index(drop=True)
    return df, errors
