"""Validaciones de datos: formato y protección contra mirar el futuro."""
import pandas as pd

BAR_COLS = {"open", "high", "low", "close", "volume"}
DAY_COLS = {"gex_bn", "em_pts", "call_wall", "put_wall", "basis", "oi_date"}


def validate_bars(bars: pd.DataFrame) -> list[str]:
    errs = []
    missing = BAR_COLS - set(bars.columns)
    if missing:
        errs.append(f"Barras: faltan columnas {sorted(missing)}")
    if not isinstance(bars.index, pd.DatetimeIndex) or bars.index.tz is None:
        errs.append("Barras: el índice debe ser fecha-hora con zona horaria (America/New_York)")
    elif str(bars.index.tz) != "America/New_York":
        errs.append(f"Barras: zona horaria debe ser America/New_York, llegó {bars.index.tz}")
    if not bars.index.is_monotonic_increasing:
        errs.append("Barras: el tiempo no está ordenado")
    if bars.index.has_duplicates:
        errs.append("Barras: hay marcas de tiempo repetidas")
    return errs


def validate_days(days: pd.DataFrame) -> list[str]:
    """oi_date = fecha del Open Interest usado. Debe ser ANTERIOR al día operado."""
    errs = []
    missing = DAY_COLS - set(days.columns)
    if missing:
        errs.append(f"Días: faltan columnas {sorted(missing)}")
        return errs
    bad = [d for d, oi in zip(days.index, days["oi_date"]) if pd.Timestamp(oi).date() >= pd.Timestamp(d).date()]
    if bad:
        errs.append(f"Días: el Open Interest NO es de un día anterior (mirar el futuro) en {len(bad)} días, p. ej. {bad[:3]}")
    return errs
