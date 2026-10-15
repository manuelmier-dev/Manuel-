"""Prueba de VIABILIDAD del flujo con signo: pide a Theta las operaciones (trades) de SPXW 0DTE pareadas con la cotización vigente (trade_quote).

Uso:  python -m bot.theta_flow_probe [fecha=2026-10-13] [hora_inicio=09:30:00] [hora_fin=09:35:00]
Mide cuántas filas hay, cuánto tarda y qué columnas trae, y guarda la muestra en ./theta_flow_probe. NO calcula nada del backtest.
*** Los nombres de parámetros de trade_quote en la v3 no se pudieron confirmar (la documentación no se pudo leer): se prueban dos formas y se muestra el error si falla.
"""
import sys
import time
from pathlib import Path

import pandas as pd

from .theta_client import build_url, fetch_text, ymd


def variants(day: str, t0: str, t1: str, symbol: str = "SPXW"):
    d8 = ymd(day)
    base = {"symbol": symbol, "expiration": d8, "strike": "*", "start_time": t0, "end_time": t1}
    yield "date", {**base, "date": d8}
    yield "start_date/end_date", {**base, "start_date": d8, "end_date": d8}


def probe(day: str, t0: str, t1: str, fetch=fetch_text, out_dir: Path | None = None) -> list[str]:
    log = []
    for name, params in variants(day, t0, t1):
        url = build_url("/option/history/trade_quote", params)
        t = time.time()
        status, text = fetch(url)
        secs = time.time() - t
        if status != 200:
            log.append(f"[{name}] HTTP {status} en {secs:.1f}s: {text[:300]}")
            continue
        lines = text.strip().splitlines()
        log.append(f"[{name}] HTTP 200 en {secs:.1f}s: {max(len(lines) - 1, 0)} filas, {len(text) / 1e6:.2f} MB")
        if lines:
            log.append("Columnas: " + lines[0][:400])
            for ln in lines[1:4]:
                log.append("   " + ln[:300])
        if out_dir is not None and len(lines) > 1:
            out_dir.mkdir(exist_ok=True)
            (out_dir / f"trade_quote_{day}_{t0.replace(':', '')}.csv").write_text(text, encoding="utf-8")
            df = pd.read_csv(pd.io.common.StringIO(text))
            log.append(f"Strikes distintos: {df['strike'].nunique() if 'strike' in df else '?'}; rango de horas: "
                       f"{df.filter(like='time').iloc[:, 0].min() if df.filter(like='time').shape[1] else '?'} a {df.filter(like='time').iloc[:, 0].max() if df.filter(like='time').shape[1] else '?'}")
            return log
    return log


if __name__ == "__main__":
    day = sys.argv[1] if len(sys.argv) > 1 else "2026-10-13"
    t0 = sys.argv[2] if len(sys.argv) > 2 else "09:30:00"
    t1 = sys.argv[3] if len(sys.argv) > 3 else "09:35:00"
    print("\n".join(probe(day, t0, t1, out_dir=Path("theta_flow_probe"))))
