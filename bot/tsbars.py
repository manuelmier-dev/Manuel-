"""Lee las barras de ES exportadas desde TradeStation con tradestation/ExportBarras5min.txt.

TradeStation numera cada barra con su hora de CIERRE; aquí se convierte a hora de INICIO (la que usa el resto del código).
La zona horaria debe ser la de Nueva York: se comprueba con el volumen (la barra de las 9:30 suele ser la de más volumen).
"""
import numpy as np
import pandas as pd

from .validate import validate_bars

NY = "America/New_York"


def load_tradestation_bars_csv(path, bar_minutes: int = 5, check_tz: bool = True) -> pd.DataFrame:
    raw = pd.read_csv(path, dtype=str)
    need = {"fecha_el", "hora_cierre", "open", "high", "low", "close", "volume"}
    if not need <= set(raw.columns):
        raise ValueError(f"Faltan columnas {sorted(need - set(raw.columns))}")
    raw = raw[raw["fecha_el"] != "fecha_el"].dropna(subset=["fecha_el"])   # el indicador puede repetir el encabezado
    raw = raw.astype({"fecha_el": "int64", "hora_cierre": "int64"})
    d = raw["fecha_el"]
    date = pd.to_datetime(((1900 + d // 10000) * 10000 + (d // 100 % 100) * 100 + d % 100).astype(str), format="%Y%m%d")
    hhmm = raw["hora_cierre"]
    close_ts = date + pd.to_timedelta(hhmm // 100, unit="h") + pd.to_timedelta(hhmm % 100, unit="m")
    start = close_ts - pd.Timedelta(minutes=bar_minutes)
    idx = pd.DatetimeIndex(start).tz_localize(NY, ambiguous="NaT", nonexistent="NaT")   # descarta las horas dudosas del cambio de horario
    out = raw[["open", "high", "low", "close", "volume"]].astype(float).set_axis(idx)
    out = out[out.index.notna()]
    out = out[~out.index.duplicated(keep="last")].sort_index()
    errs = validate_bars(out)
    if errs:
        raise ValueError("; ".join(errs))
    if check_tz:
        frac = open_bar_share(out)
        if frac < 0.5:
            raise ValueError(f"Solo en {frac:.0%} de los días la barra de más volumen cae a las 9:30. "
                             "Probablemente la gráfica no está en hora de Nueva York.")
    return out


def open_bar_share(bars: pd.DataFrame) -> float:
    """Proporción de días en que la barra de más volumen entre 9:00 y 11:00 NY empieza a las 9:30."""
    win = bars.between_time("09:00", "10:55")
    if win.empty:
        return 0.0
    hits = win.groupby(win.index.date)["volume"].apply(lambda s: s.idxmax().strftime("%H:%M") == "09:30")
    return float(hits.mean())


def check_bars(bars: pd.DataFrame) -> dict:
    days = pd.Series(bars.index.date, index=bars.index)
    rth = bars.between_time("09:30", "15:55")
    full = (rth.groupby(rth.index.date).size() >= 70).sum()
    pre = bars.between_time("09:00", "09:25")
    return {"barras": len(bars), "desde": str(bars.index[0]), "hasta": str(bars.index[-1]),
            "dias": int(days.nunique()), "dias_con_sesion_completa": int(full),
            "dias_con_premercado_9_a_9_25": int(pre.groupby(pre.index.date).size().gt(0).sum())}
