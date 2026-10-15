"""Reporte de operaciones por año y antes/después de costos.

Uso:  python -m bot.trades_report <operaciones.csv>
Los costos por operación: comisión (config) + deslizamiento 2 x 0.25 pts x 50 USD. El resultado "antes de costos" los suma de vuelta.
"""
import sys

import pandas as pd

from .config import Params


def by_period(trades: pd.DataFrame, freq: str = "year", p: Params = Params()) -> pd.DataFrame:
    t = trades.copy()
    t["fecha"] = pd.to_datetime(t["date"])
    cost = p.commission_rt + 2 * p.slippage_pts * p.point_value
    t["usd_antes_costos"] = t["usd"] + cost
    key = t["fecha"].dt.year if freq == "year" else t["fecha"].dt.to_period("Q").astype(str)
    rows = []
    for k, g in t.groupby(key):
        w, l = g.loc[g["usd"] > 0, "usd"], g.loc[g["usd"] <= 0, "usd"]
        rows.append({"periodo": k, "operaciones": len(g), "aciertos_%": round(100 * len(w) / len(g), 1), "usd_por_operacion": round(g["usd"].mean(), 1),
                     "total_usd": round(g["usd"].sum(), 0), "factor_ganancia": round(w.sum() / abs(l.sum()), 2) if len(l) and l.sum() else None,
                     "total_antes_de_costos": round(g["usd_antes_costos"].sum(), 0)})
    return pd.DataFrame(rows)


if __name__ == "__main__":
    tr = pd.read_csv(sys.argv[1])
    pd.set_option("display.width", 200)
    print("== Por año ==")
    print(by_period(tr, "year").to_string(index=False))
    print("\n== Por trimestre ==")
    print(by_period(tr, "quarter").to_string(index=False))
    print(f"\nCosto por operación supuesto: {Params().commission_rt + 2 * Params().slippage_pts * Params().point_value:.0f} USD (comisión + deslizamiento de entrada y salida).")
