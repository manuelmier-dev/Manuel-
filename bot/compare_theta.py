"""Compara, día por día, el resumen calculado con Theta contra el de las cadenas de TradeStation (mismos días).

Uso:  python -m bot.compare_theta theta_resumen.csv resumen_cadenas.csv
Sirve para validar la fuente Theta ANTES de bajar años de historia: el Open Interest y los walls deben coincidir casi siempre;
la gamma (GEX) difiere un poco porque Theta no la trae y aquí se estima con las cotizaciones.
"""
import sys

import numpy as np
import pandas as pd

COLS = ["spot", "em_proxy", "gex_bn", "call_wall_oi", "put_wall_oi", "call_wall_oi_1em", "put_wall_oi_1em", "call_wall_gex", "put_wall_gex"]


def compare(theta: pd.DataFrame, ts: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    t = theta.assign(date=pd.to_datetime(theta["date"]).dt.date).drop_duplicates("date", keep="last").set_index("date")
    s = ts.assign(date=pd.to_datetime(ts["date"]).dt.date).drop_duplicates("date", keep="last").set_index("date")
    days = sorted(set(t.index) & set(s.index))
    cols = [c for c in COLS if c in t.columns and c in s.columns]
    d = pd.DataFrame(index=days)
    for c in cols:
        d[f"{c}_theta"], d[f"{c}_ts"] = t.loc[days, c].astype(float), s.loc[days, c].astype(float)
        d[f"{c}_dif"] = d[f"{c}_theta"] - d[f"{c}_ts"]
    lines = [f"Días en común: {len(days)} (Theta: {len(t)}, TradeStation: {len(s)})"]
    for c in cols:
        x = d[f"{c}_dif"].dropna()
        if not len(x):
            continue
        if c.endswith(("wall_oi", "wall_oi_1em", "wall_gex")):
            lines.append(f"{c}: mismo strike en {int((x == 0).sum())} de {len(x)} días; diferencia mediana {x.abs().median():.0f} pts")
        else:
            lines.append(f"{c}: diferencia mediana {x.abs().median():.2f}, máxima {x.abs().max():.2f}")
    if "gex_bn_theta" in d and d[["gex_bn_theta", "gex_bn_ts"]].dropna().shape[0] > 2:
        g = d[["gex_bn_theta", "gex_bn_ts"]].dropna()
        same = int((np.sign(g["gex_bn_theta"]) == np.sign(g["gex_bn_ts"])).sum())
        lines.append(f"GEX: mismo signo (reversión/tendencia) en {same} de {len(g)} días; correlación {g.corr().iloc[0, 1]:.2f}")
    return d, lines


if __name__ == "__main__":
    table, lines = compare(pd.read_csv(sys.argv[1]), pd.read_csv(sys.argv[2]))
    print("\n".join(lines))
    table.to_csv("comparacion_theta_vs_tradestation.csv")
    print("Detalle guardado en comparacion_theta_vs_tradestation.csv")
