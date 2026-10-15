"""Evalúa las reglas PRE-REGISTRADAS F1-F4 del flujo con signo (escritas ANTES de ver resultados).

Presión de cobertura P = -(suma de dealer_delta de 9:30 a 10:30). P > 0: los dealers compran futuros para cubrirse (empuje alcista).
G = suma de dealer_gamma (G < 0: dealers cortos gamma). Decisión a las 10:30 (con barras ya cerradas), 1 operación/día, 1 contrato ES.
  F1: va en la dirección de P (largo si P>0, corto si P<0).
  F2: contra P (la apuesta contraria).
  F3: como F1, solo si |P| supera la mediana de |P| de los días anteriores (sin mirar el futuro).
  F4: como F1, solo si G < 0.
Salidas: a las 15:55 y a las 12:30 (variante 2 h). Costo 29 USD por operación. Placebo: se baraja el signo de P entre días (2000 veces).
Corrección: 4 reglas x 2 salidas = 8 pruebas -> exige |t| > 2.7 (Bonferroni aprox. a 5%) Y los 3 periodos (primero/medio/último tercio) con el mismo signo.

Uso: python -m bot.flow_eval <carpeta_con_flow/> <barras_ES.csv>
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from .journal import load_es_bars_csv

POINT_USD, COST_USD, N_TESTS, T_BAR = 50.0, 29.0, 8, 2.7
RULES = ["F1", "F2", "F3", "F4"]
EXITS = {"15:55": "15:55", "2h": "12:30"}


def day_features(flow_dir) -> pd.DataFrame:
    rows = []
    for f in sorted(Path(flow_dir).glob("*.csv")):
        d = pd.read_csv(f)
        if d.empty or d["vol_clasif"].sum() == 0:
            continue
        rows.append({"date": pd.Timestamp(f.stem), "P": -d["dealer_delta"].sum(), "G": d["dealer_gamma"].sum(),
                     "vol": d["vol"].sum(), "pct_clasif": d["vol_clasif"].sum() / d["vol"].sum()})
    return pd.DataFrame(rows).set_index("date") if rows else pd.DataFrame(columns=["P", "G", "vol", "pct_clasif"])


def directions(feat: pd.DataFrame) -> pd.DataFrame:
    base = np.sign(feat["P"])
    med = feat["P"].abs().expanding().median().shift(1)
    return pd.DataFrame({"F1": base, "F2": -base, "F3": base.where(feat["P"].abs() > med, 0), "F4": base.where(feat["G"] < 0, 0)})


def day_moves(es: pd.DataFrame, dates, exit_hhmm: str) -> pd.Series:
    """Puntos de ES entre la apertura de la barra de 10:30 y la de la salida (misma sesión)."""
    out = {}
    for d in dates:
        day = pd.Timestamp(d).strftime("%Y-%m-%d")
        try:
            a = es.loc[pd.Timestamp(f"{day} 10:30", tz="America/New_York"), "open"]
            b = es.loc[pd.Timestamp(f"{day} {exit_hhmm}", tz="America/New_York"), "open"]
        except KeyError:
            continue
        out[pd.Timestamp(d)] = float(b) - float(a)
    return pd.Series(out, dtype=float)


def tstat(x: np.ndarray) -> float:
    return float(x.mean() / (x.std(ddof=1) / np.sqrt(len(x)))) if len(x) > 2 and x.std(ddof=1) > 0 else float("nan")


def evaluate(feat: pd.DataFrame, es: pd.DataFrame, n_placebo: int = 2000, seed: int = 7) -> pd.DataFrame:
    dirs, rng, rows = directions(feat), np.random.default_rng(seed), []
    for ex_name, ex_time in EXITS.items():
        mv = day_moves(es, feat.index, ex_time)
        for rule in RULES:
            s = dirs[rule].reindex(mv.index).fillna(0)
            take = s != 0
            pnl = (s[take] * mv[take]) * POINT_USD - COST_USD
            if len(pnl) < 10:
                rows.append({"regla": rule, "salida": ex_name, "n": int(len(pnl))})
                continue
            x = pnl.to_numpy()
            thirds = np.array_split(x, 3)
            base_sign, mvt = np.sign(feat["P"]).reindex(mv.index)[take].to_numpy(), mv[take].to_numpy()
            shuffled = [float(np.mean(rng.permutation(base_sign) * (1 if rule != "F2" else -1) * mvt) * POINT_USD - COST_USD) for _ in range(n_placebo)]
            t = tstat(x)
            same = all(np.sign(p.mean()) == np.sign(x.mean()) for p in thirds)
            rows.append({"regla": rule, "salida": ex_name, "n": len(x), "usd_prom": x.mean(), "usd_total": x.sum(), "pct_gana": float((x > 0).mean()),
                         "t": t, "placebo_p": float((np.array(shuffled) >= x.mean()).mean()),
                         "tercios_usd": " | ".join(f"{p.mean():+.0f}" for p in thirds),
                         "veredicto": "CANDIDATA" if (t > T_BAR and same) else "SIN VENTAJA"})
    return pd.DataFrame(rows)


if __name__ == "__main__":
    feat = day_features(sys.argv[1])
    print(f"Días con flujo: {len(feat)}; % de volumen clasificado (mediana): {feat['pct_clasif'].median():.0%}" if len(feat) else "Sin días")
    if len(feat):
        pd.set_option("display.width", 200)
        print(evaluate(feat, load_es_bars_csv(sys.argv[2])).to_string(index=False))
        print(f"\nBarra: |t| > {T_BAR} (Bonferroni, {N_TESTS} pruebas) y los 3 tercios con el mismo signo. Es un PROXY del flujo real.")
