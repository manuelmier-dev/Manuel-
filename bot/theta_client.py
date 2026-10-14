"""Cliente mínimo de la API REST v3 de Theta Terminal (http://127.0.0.1:25503/v3).

*** NO PROBADO contra la API real: Claude no tiene acceso a Theta. Los nombres de endpoints y parámetros salen de la documentación
*** pública (consultada el 14-oct-2026); `python -m bot.theta_probe` los comprueba y guarda las respuestas reales para ajustar este archivo.

Hechos de la documentación:
- Requiere Theta Terminal v3 en marcha (Java 21+, creds.txt junto al .jar). Una sola sesión por cuenta (error 478) y fijada a una IP (476).
- /option/at_time/quote: última cotización NBBO a la hora pedida (America/New_York). Usar horas "redondas" (09:20:00.000); con segundos y
  expiration=* puede tardar o colgarse.
- Open Interest: lo publica OPRA ~06:30 ET y representa el cierre del día anterior.
- Plan Standard: 2 hilos de servidor; se hace una solicitud a la vez y se espacian.
"""
import io
import time
import urllib.error
import urllib.parse
import urllib.request

import pandas as pd

BASE = "http://127.0.0.1:25503/v3"


class ThetaError(RuntimeError):
    def __init__(self, status, text):
        super().__init__(f"HTTP {status}: {text[:200]}")
        self.status, self.text = status, text


def fetch_text(url: str, timeout: int = 180) -> tuple[int, str]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


def build_url(path: str, params: dict) -> str:
    return f"{BASE}{path}?" + urllib.parse.urlencode({**params, "format": "csv"}, safe="*:")


def get_frame(path: str, params: dict, fetch=fetch_text, tries: int = 4, pause: float = 5.0) -> pd.DataFrame:
    """GET con reintentos para 429/5xx. Errores de sesión (476/478) y 4xx no se reintentan."""
    url = build_url(path, params)
    for k in range(tries):
        status, text = fetch(url)
        if status == 200:
            return pd.read_csv(io.StringIO(text)) if text.strip() else pd.DataFrame()
        if status in (476, 478):
            raise ThetaError(status, "Otra sesión del Theta Terminal está activa o la IP cambió. Cierra el otro terminal.")
        if status == 429 or status >= 500:
            time.sleep(pause * (k + 1))
            continue
        raise ThetaError(status, text)
    raise ThetaError(status, "Reintentos agotados: " + text)


def ymd(d) -> str:
    return pd.Timestamp(d).strftime("%Y%m%d")


def list_expirations(symbol: str = "SPXW", fetch=fetch_text) -> pd.DataFrame:
    return get_frame("/option/list/expirations", {"symbol": symbol}, fetch)


def at_time_quote(symbol: str, expiration, date, time_of_day: str = "09:20:00.000", fetch=fetch_text) -> pd.DataFrame:
    return get_frame("/option/at_time/quote", {"symbol": symbol, "expiration": ymd(expiration), "strike": "*",
                                               "start_date": ymd(date), "end_date": ymd(date), "time_of_day": time_of_day}, fetch)


def open_interest(symbol: str, expiration, date, fetch=fetch_text) -> pd.DataFrame:
    """La documentación de v3 no me deja claro si el parámetro es `date` o `start_date`/`end_date`: se prueban las dos formas."""
    last = None
    for extra in ({"date": ymd(date)}, {"start_date": ymd(date), "end_date": ymd(date)}):
        try:
            df = get_frame("/option/history/open_interest", {"symbol": symbol, "expiration": ymd(expiration), "strike": "*", **extra}, fetch)
        except ThetaError as e:
            last = e
            continue
        if len(df):
            return df
    if last:
        raise last
    return pd.DataFrame()


def _col(df: pd.DataFrame, *names: str) -> str:
    low = {c.lower(): c for c in df.columns}
    for n in names:
        if n in low:
            return low[n]
    raise KeyError(f"Falta una columna de {names}; columnas recibidas: {list(df.columns)}")


def _strike(s: pd.Series) -> pd.Series:
    s = pd.to_numeric(s, errors="coerce")
    return s / 1000.0 if s.median() > 100000 else s                      # v2 manda décimas de centavo; v3, dólares


def _right(s: pd.Series) -> pd.Series:
    return s.astype(str).str.strip().str.upper().str[0]


def normalize_quotes(df: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({"strike": _strike(df[_col(df, "strike")]), "right": _right(df[_col(df, "right")]),
                         "bid": pd.to_numeric(df[_col(df, "bid")], errors="coerce"),
                         "ask": pd.to_numeric(df[_col(df, "ask")], errors="coerce")}).dropna(subset=["strike"])


def normalize_oi(df: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame({"strike": _strike(df[_col(df, "strike")]), "right": _right(df[_col(df, "right")]),
                        "open_interest": pd.to_numeric(df[_col(df, "open_interest", "openinterest", "oi")], errors="coerce")})
    if any(c.lower() == "timestamp" for c in df.columns):               # si trae varias filas por contrato, la última del día
        out = out.assign(_t=df[_col(df, "timestamp")]).sort_values("_t").drop(columns="_t")
    return out.dropna(subset=["strike"]).drop_duplicates(["strike", "right"], keep="last")
