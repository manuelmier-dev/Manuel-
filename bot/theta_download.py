"""Baja la historia 0DTE de SPXW desde Theta Terminal y guarda un resumen por día. Reanuda donde se quedó.

Uso (en el servidor donde corre Theta Terminal, FUERA del horario de mercado):
  python -m bot.theta_download <carpeta_de_salida> <desde AAAA-MM-DD> <hasta AAAA-MM-DD> [SPXW]
Salida:  theta_resumen.csv (una fila por día), tables/AAAA-MM-DD.csv (strike, oi_c, oi_p), theta_errores.csv
"""
import sys
import time
from pathlib import Path

import pandas as pd

from .theta_client import (ThetaError, at_time_quote, fetch_text, list_expirations, normalize_oi, normalize_quotes,
                           open_interest)
from .theta_snapshot import summary_from_table, summary_from_theta

MIN_STRIKES = 20


def expiration_days(symbol: str, fetch=fetch_text) -> list[pd.Timestamp]:
    df = list_expirations(symbol, fetch)
    col = next((c for c in df.columns if "expiration" in c.lower() or "date" in c.lower()), df.columns[0])
    return sorted(pd.to_datetime(df[col].astype(str).str.replace("-", ""), format="%Y%m%d", errors="coerce").dropna().unique())


def download_range(out_dir, start, end, symbol: str = "SPXW", fetch=fetch_text, pause: float = 0.3, log=print) -> dict:
    out = Path(out_dir)
    (out / "tables").mkdir(parents=True, exist_ok=True)
    (out / "raw").mkdir(exist_ok=True)
    resumen, errores = out / "theta_resumen.csv", out / "theta_errores.csv"
    days = [d for d in expiration_days(symbol, fetch) if pd.Timestamp(start) <= d <= pd.Timestamp(end) and d.weekday() < 5]
    done = ok = failed = 0
    for d in days:
        table_path = out / "tables" / f"{d.date()}.csv"
        if table_path.exists():
            done += 1
            continue
        try:
            q = normalize_quotes(at_time_quote(symbol, d, d, fetch=fetch))
            oi = normalize_oi(open_interest(symbol, d, d, fetch=fetch))
            row = summary_from_theta(d, q, oi)
            if row["n_strikes"] < MIN_STRIKES:
                raise ValueError(f"solo {row['n_strikes']} strikes con cotización válida")
            row.pop("_raw").to_csv(out / "raw" / f"{d.date()}.csv", index=False)   # cotizaciones+OI en crudo: permite recalcular sin la API
            row.pop("_table").to_csv(table_path, index=False)          # la tabla se guarda al final: si algo falla, el día se reintenta
            pd.DataFrame([row]).to_csv(resumen, mode="a", header=not resumen.exists(), index=False)
            ok += 1
        except ThetaError as e:
            if e.status in (476, 478):
                raise
            failed += 1
            pd.DataFrame([{"date": d.date(), "error": str(e)}]).to_csv(errores, mode="a", header=not errores.exists(), index=False)
        except Exception as e:  # noqa: BLE001 - se registra el día y el motivo, no se oculta
            failed += 1
            pd.DataFrame([{"date": d.date(), "error": str(e)}]).to_csv(errores, mode="a", header=not errores.exists(), index=False)
        if (ok + failed) % 25 == 0:
            log(f"{d.date()}  ok={ok} fallidos={failed} ya_hechos={done} de {len(days)}")
        time.sleep(pause)
    return {"dias": len(days), "nuevos": ok, "fallidos": failed, "ya_hechos": done}


def recompute_from_raw(folder) -> int:
    """Rehace theta_resumen.csv y tables/ desde raw/ SIN llamar a la API (después de corregir el método de cálculo)."""
    f = Path(folder)
    rows = []
    for p in sorted((f / "raw").glob("*.csv")):
        row = summary_from_table(pd.Timestamp(p.stem), pd.read_csv(p))
        row.pop("_table").to_csv(f / "tables" / f"{p.stem}.csv", index=False)
        rows.append(row)
    pd.DataFrame(rows).to_csv(f / "theta_resumen.csv", index=False)
    return len(rows)


def load_theta_folder(folder) -> tuple[pd.DataFrame, list[str]]:
    """Lee la carpeta de salida de download_range y devuelve lo mismo que summarize_folder."""
    f = Path(folder)
    df = pd.read_csv(f / "theta_resumen.csv", parse_dates=["date"]).sort_values("date").drop_duplicates("date", keep="last")
    df["date"] = df["date"].dt.date
    df["_table"] = [pd.read_csv(f / "tables" / f"{d}.csv") for d in df["date"]]
    errors = []
    if (f / "theta_errores.csv").exists():
        errors = [f"{r.date}: {r.error}" for r in pd.read_csv(f / "theta_errores.csv").itertuples()]
    return df.reset_index(drop=True), errors


if __name__ == "__main__":
    if sys.argv[1] == "--recalcular":                                  # python -m bot.theta_download --recalcular <carpeta>
        print({"dias_recalculados": recompute_from_raw(sys.argv[2])})
        sys.exit(0)
    out_dir, start, end = sys.argv[1], sys.argv[2], sys.argv[3]
    print(download_range(out_dir, start, end, sys.argv[4] if len(sys.argv) > 4 else "SPXW"))
