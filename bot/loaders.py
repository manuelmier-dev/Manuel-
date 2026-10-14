"""Lee las cadenas SPX 0DTE exportadas de TradeStation (.xls o .csv) y calcula el resumen del día.

Hay dos formatos de archivo:
- completo (septiembre en adelante): con símbolo, gamma, volatilidad, volumen y delta.
- sin gamma (agosto): solo Open Interest, delta, bid, ask y strike. La gamma se calcula a partir de los precios
  (ver bot.gex.gamma_from_quotes; se validó contra archivos que sí traen gamma).

Look-ahead: el nombre del archivo trae la hora de exportación (hora de Mérida, SUPUESTO). Si es posterior a las
9:30 de Nueva York, el archivo se rechaza, porque los precios ya no son de antes de la apertura.
"""
import re
from pathlib import Path

import numpy as np
import pandas as pd

from .gex import expected_move, gamma_exposure, gamma_from_quotes

NAME_TZ = "America/Merida"      # zona de la hora que aparece en el nombre del archivo (SUPUESTO; ajustable)
NY = "America/New_York"
OPEN_NY = pd.Timestamp("09:30").time()
GEX_WINDOW_PTS = 90.0           # el GEX se calcula con los strikes a ±90 pts del precio (los archivos viejos llegan a -83 y +79), para comparar archivos de distinto ancho

# columnas del formato completo: calls a la izquierda, strike al centro, puts a la derecha
C = dict(symbol=1, gamma=2, iv=3, oi=5, bid=7, ask=8)
STRIKE = 9
P = dict(bid=10, ask=11, oi=13, iv=14, gamma=16)
# columnas del formato sin gamma
NG = dict(c_oi=1, c_delta=2, c_bid=3, c_ask=4, strike=5, p_bid=6, p_ask=7, p_delta=8, p_oi=9)


def _num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s.astype(str).str.replace(",", "").str.replace("%", "").str.strip(), errors="coerce")


def date_from_filename(path) -> pd.Timestamp:
    m = re.search(r"(\d{2})-(\d{2})-(\d{4})", Path(path).name)
    if not m:
        raise ValueError(f"No encuentro la fecha (dd-mm-aaaa) en el nombre: {Path(path).name}")
    return pd.Timestamp(year=int(m[3]), month=int(m[2]), day=int(m[1]))


def snapshot_et_from_filename(path, trade_date: pd.Timestamp):
    """Hora de exportación en Nueva York, tomada del nombre ('7.20am', hora de Mérida). None si no hay hora."""
    m = re.search(r"(\d{1,2})[.:](\d{2})\s*([ap])m", Path(path).name, re.I)
    if not m:
        return None
    h = int(m[1]) % 12 + (12 if m[3].lower() == "p" else 0)
    local = pd.Timestamp(year=trade_date.year, month=trade_date.month, day=trade_date.day, hour=h, minute=int(m[2]))
    return local.tz_localize(NAME_TZ).tz_convert(NY)


def _header_text(raw: pd.DataFrame) -> str:
    return " ".join(raw[0].dropna().astype(str))


def _em_tradestation(raw: pd.DataFrame) -> float:
    m = re.search(r"Custom=\(±([\d.]+)\)", _header_text(raw))   # "(Custom=(±22.83))"
    return float(m[1]) if m else float("nan")


def _spot_by_parity(z: pd.DataFrame) -> float:
    ok = z.dropna(subset=["mid_c", "mid_p"])
    near = ok.iloc[(ok["mid_c"] - ok["mid_p"]).abs().argsort()[:5]]
    return float((near["strike"] + near["mid_c"] - near["mid_p"]).median())


def _max_oi_strike(side: pd.DataFrame, col: str) -> float:
    side = side.dropna(subset=[col])
    if side.empty or side[col].max() <= 0:
        return float("nan")
    return float(side.loc[side[col].idxmax(), "strike"])


def _layout(raw: pd.DataFrame) -> str:
    return "completo" if "Gamma" in raw.iloc[1].astype(str).tolist() else "sin_gamma"


def _table_full(raw: pd.DataFrame, trade_date: pd.Timestamp) -> pd.DataFrame:
    rows = raw[raw[C["symbol"]].astype(str).str.startswith("SPXW")].copy()
    if rows.empty:
        raise ValueError("No hay filas SPXW en el archivo")
    rows["exp"] = rows[C["symbol"]].str.extract(r"SPXW (\d{6})")[0]
    expected_exp = trade_date.strftime("%y%m%d")
    rows = rows[rows["exp"] == expected_exp]
    if rows.empty:
        raise ValueError(f"El archivo no trae el vencimiento 0DTE {expected_exp}")
    z = pd.DataFrame({
        "strike": _num(rows[STRIKE]), "g_c": _num(rows[C["gamma"]]), "oi_c": _num(rows[C["oi"]]),
        "bid_c": _num(rows[C["bid"]]), "ask_c": _num(rows[C["ask"]]),
        "g_p": _num(rows[P["gamma"]]), "oi_p": _num(rows[P["oi"]]),
        "bid_p": _num(rows[P["bid"]]), "ask_p": _num(rows[P["ask"]]),
    }).reset_index(drop=True)
    z["mid_c"] = (z["bid_c"] + z["ask_c"]) / 2
    z["mid_p"] = (z["bid_p"] + z["ask_p"]) / 2
    return z


def _table_no_gamma(raw: pd.DataFrame, trade_date: pd.Timestamp) -> pd.DataFrame:
    m = re.search(r"(\d{1,2}) ([A-Za-z]{3}) (\d{2})\b", _header_text(raw))
    if not m or "(0d)" not in _header_text(raw):
        raise ValueError("El encabezado no indica un vencimiento 0DTE")
    if pd.to_datetime(f"{m[1]} {m[2]} {m[3]}", format="%d %b %y").date() != trade_date.date():
        raise ValueError(f"El vencimiento del archivo ({m[0]}) no es el del día {trade_date.date()}")
    body = raw.iloc[3:]
    z = pd.DataFrame({
        "strike": _num(body[NG["strike"]]), "d_c": _num(body[NG["c_delta"]]),
        "oi_c": _num(body[NG["c_oi"]]), "oi_p": _num(body[NG["p_oi"]]),
        "bid_c": _num(body[NG["c_bid"]]), "ask_c": _num(body[NG["c_ask"]]),
        "bid_p": _num(body[NG["p_bid"]]), "ask_p": _num(body[NG["p_ask"]]),
    }).dropna(subset=["strike"]).sort_values("strike").reset_index(drop=True)
    # filas basura al final del archivo (precios absurdos): la delta del call nunca puede subir al alejarse
    keep, prev = [], 1.01
    for d in z["d_c"]:
        ok = bool(pd.notna(d) and d <= prev + 0.02)
        keep.append(ok)
        if ok:
            prev = d
    z = z[keep].reset_index(drop=True)
    z["mid_c"] = (z["bid_c"] + z["ask_c"]) / 2
    z["mid_p"] = (z["bid_p"] + z["ask_p"]) / 2
    return z


def parse_chain_frame(raw: pd.DataFrame, trade_date: pd.Timestamp, snapshot_et=None) -> dict:
    """raw: la hoja leída sin encabezados. Devuelve el resumen del día para el vencimiento 0DTE."""
    layout = _layout(raw)
    z = _table_full(raw, trade_date) if layout == "completo" else _table_no_gamma(raw, trade_date)
    spot = _spot_by_parity(z)
    if layout == "completo":
        g_c, g_p = z["g_c"], z["g_p"]
    else:
        g_c = g_p = pd.Series(gamma_from_quotes(z["strike"], z["mid_c"], z["mid_p"], spot).values, index=z.index)

    chain = pd.concat([
        pd.DataFrame({"strike": z["strike"], "right": "C", "gamma": g_c, "open_interest": z["oi_c"]}),
        pd.DataFrame({"strike": z["strike"], "right": "P", "gamma": g_p, "open_interest": z["oi_p"]}),
    ]).dropna()
    quotes = pd.concat([
        pd.DataFrame({"strike": z["strike"], "right": "C", "mid": z["mid_c"]}),
        pd.DataFrame({"strike": z["strike"], "right": "P", "mid": z["mid_p"]}),
    ]).dropna()
    g_all = gamma_exposure(chain, spot)
    g = gamma_exposure(chain[(chain["strike"] - spot).abs() <= GEX_WINDOW_PTS], spot)
    em_ts = _em_tradestation(raw)
    em_straddle = expected_move(quotes, spot)
    em_ref = em_ts if pd.notna(em_ts) else em_straddle
    call_1em = _max_oi_strike(z[(z["strike"] >= spot) & (z["strike"] <= spot + em_ref)], "oi_c")
    put_1em = _max_oi_strike(z[(z["strike"] <= spot) & (z["strike"] >= spot - em_ref)], "oi_p")
    return {
        "date": trade_date.date(),
        "snapshot_et": snapshot_et.strftime("%H:%M") if snapshot_et is not None else "",
        "gamma_fuente": "archivo" if layout == "completo" else "estimada",
        "spot": spot,
        "em_straddle": em_straddle,
        "em_tradestation": em_ts,
        "gex_bn": g["total_bn"],
        "gex_bn_total": g_all["total_bn"],            # con todos los strikes del archivo
        "gex_ratio": g["total_bn"] / g["gross_bn"] if g["gross_bn"] else float("nan"),  # neto / total, entre -1 y 1
        "call_wall_gex": g["call_wall"],
        "put_wall_gex": g["put_wall"],
        "call_wall_oi": float(z.loc[z["oi_c"].idxmax(), "strike"]),
        "put_wall_oi": float(z.loc[z["oi_p"].idxmax(), "strike"]),
        "call_wall_oi_1em": call_1em,                 # mayor OI de calls entre el precio y +1 EM
        "put_wall_oi_1em": put_1em,                   # mayor OI de puts entre -1 EM y el precio
        "strike_min": float(z["strike"].min()),
        "strike_max": float(z["strike"].max()),
        "n_strikes": int(len(z)),
    }


def read_raw(path) -> pd.DataFrame:
    if str(path).lower().endswith(".csv"):
        return pd.read_csv(path, header=None, dtype=str, encoding="cp1252", names=list(range(19)))
    return pd.read_excel(path, header=None, engine="xlrd")


def load_chain_file(path, allow_late: bool = False) -> dict:
    trade_date = date_from_filename(path)
    snap = snapshot_et_from_filename(path, trade_date)
    if snap is not None and snap.time() > OPEN_NY and not allow_late:
        raise ValueError(f"exportado a las {snap:%H:%M} de Nueva York, después de la apertura (no sirve para decidir antes de las 9:30)")
    out = parse_chain_frame(read_raw(path), trade_date, snap)
    out["file"] = Path(path).name
    return out


def summarize_folder(folder, patterns=("**/*.xls", "**/*.csv")) -> tuple[pd.DataFrame, list[str]]:
    """Resume todos los archivos; los que fallan se reportan, no se ocultan. Si hay dos del mismo día, queda el más tardío válido."""
    rows, errors = [], []
    files = sorted({f for p in patterns for f in Path(folder).glob(p)})
    for f in files:
        try:
            rows.append(load_chain_file(f))
        except Exception as e:  # noqa: BLE001 - se reporta el archivo y el motivo
            errors.append(f"{f.name}: {e}")
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values(["date", "snapshot_et"]).drop_duplicates("date", keep="last").reset_index(drop=True)
    return df, errors
