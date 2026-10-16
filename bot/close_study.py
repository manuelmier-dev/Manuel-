"""ETAPA 1 de ESTRATEGIA_0DTE_CIERRE.md: ¿las señales conocidas a las 15:45 predicen cuánto se mueve el ES entre 15:45 y 16:00?
No usa precios de opciones. Si aquí no hay relación, no se pasa a la Etapa 2.

Resultado Z = movimiento de 15:45 a 16:00 dividido entre su mediana de los 20 días previos (sin mirar el futuro). Dos versiones:
  Z_mov = |cierre 15:55 - apertura 15:45|;   Z_rng = máximo - mínimo de las barras 15:45-15:55.
Señales (hipótesis con signo, pre-registradas):  S1_gex (gex_bn, GEX más negativo => más movimiento: signo -),
  S2_dist (distancia a la pared de OI más cercana, en movimientos esperados: lejos => más movimiento: +),
  S3_rng (rango 15:00-15:45 / mediana 20 días: +), S5_vol (volumen ES 15:00-15:45 / mediana 20 días: +; es el volumen del FUTURO,
  no el de opciones 0DTE, que llega con la descarga de flujo), S6_imp (|retorno 15:00-15:45| / mediana 20 días: +).
Veredicto: 10 pruebas (5 señales x 2 resultados) -> p < 0.005 (permutación) Y los 3 tercios del tiempo con el signo previsto.
Uso:  python -m bot.close_study <carpeta_theta> <barras_ES.csv>
"""
import sys

import numpy as np
import pandas as pd

NY = "America/New_York"
N_TESTS, P_BAR, LOOKBACK = 10, 0.05 / 10, 20
SIGNALS = {"S1_gex": -1, "S2_dist": +1, "S3_rng": +1, "S5_vol": +1, "S6_imp": +1}
OUTCOMES = ["Z_mov", "Z_rng"]


def _ts(day, hhmm):
    return pd.Timestamp(f"{pd.Timestamp(day).date()} {hhmm}", tz=NY)


def raw_day_features(bars: pd.DataFrame, day, center_spx: float, basis: float, call_wall: float, put_wall: float, em: float, gex: float) -> dict | None:
    """Todo lo que se sabe a las 15:45 y lo que pasó después. bars: índice = INICIO de la barra de 5 min."""
    try:
        a = bars.loc[_ts(day, "15:00"):_ts(day, "15:40")]
        post = bars.loc[_ts(day, "15:45"):_ts(day, "15:55")]
        if len(a) < 8 or len(post) < 3 or _ts(day, "15:45") not in bars.index or _ts(day, "15:55") not in bars.index:
            return None
    except KeyError:
        return None
    open_1545 = float(post["open"].iloc[0])
    spot = open_1545 - basis
    walls = [w for w in (call_wall, put_wall) if pd.notna(w)]
    dist = min(abs(spot - w) for w in walls) / em if walls and em and em > 0 else np.nan
    return {"date": pd.Timestamp(day), "S1_gex": gex, "S2_dist": dist,
            "S3_rng": float(a["high"].max() - a["low"].min()), "S5_vol": float(a["volume"].sum()),
            "S6_imp": abs(float(a["close"].iloc[-1]) - float(a["open"].iloc[0])),
            "Y_mov": abs(float(post["close"].iloc[-1]) - open_1545), "Y_rng": float(post["high"].max() - post["low"].min())}


def normalize(df: pd.DataFrame) -> pd.DataFrame:
    """Divide cada medida de rango/volumen entre su mediana de los 20 días ANTERIORES (shift(1))."""
    d = df.sort_values("date").set_index("date").copy()
    for c, out in (("S3_rng", "S3_rng"), ("S5_vol", "S5_vol"), ("S6_imp", "S6_imp"), ("Y_mov", "Z_mov"), ("Y_rng", "Z_rng")):
        d[out] = d[c] / d[c].rolling(LOOKBACK, min_periods=LOOKBACK).median().shift(1)
    return d.drop(columns=["Y_mov", "Y_rng"]).dropna(subset=["Z_mov", "Z_rng"] + [s for s in SIGNALS if s != "S1_gex" and s != "S2_dist"])


def evaluate(d: pd.DataFrame, n_perm: int = 5000, seed: int = 11) -> pd.DataFrame:
    rng, rows = np.random.default_rng(seed), []
    for sig, sign in SIGNALS.items():
        for out in OUTCOMES:
            x = d[[sig, out]].dropna()
            if len(x) < 60:
                rows.append({"señal": sig, "resultado": out, "n": len(x)})
                continue
            rx, ry = x[sig].rank().to_numpy(), x[out].rank().to_numpy()
            rho = float(np.corrcoef(rx, ry)[0, 1])
            perm = np.array([np.corrcoef(rx, rng.permutation(ry))[0, 1] for _ in range(n_perm)])
            p = float((np.abs(perm) >= abs(rho)).mean())
            parts = [x.iloc[i] for i in np.array_split(np.arange(len(x)), 3)]
            thirds = [float(np.corrcoef(c[sig].rank(), c[out].rank())[0, 1]) for c in parts]
            ok = p < P_BAR and np.sign(rho) == sign and all(np.sign(t) == sign for t in thirds)
            rows.append({"señal": sig, "resultado": out, "n": len(x), "rho": rho, "p_azar": p, "signo_previsto": sign,
                         "rho_tercios": " | ".join(f"{t:+.2f}" for t in thirds), "veredicto": "RELACIÓN" if ok else "SIN RELACIÓN"})
    return pd.DataFrame(rows)


def build(folder, bars: pd.DataFrame) -> pd.DataFrame:
    from .days import build_days
    from .loaders import summarize_folder
    summary, _ = summarize_folder(folder)
    days, _ = build_days(summary, bars)
    rows = [raw_day_features(bars, d, r["center_spx"], r["basis"], r["call_wall"], r["put_wall"], r["em_pts"], r["gex_bn"]) for d, r in days.iterrows()]
    return normalize(pd.DataFrame([r for r in rows if r]))


if __name__ == "__main__":
    from .journal import load_es_bars_csv
    d = build(sys.argv[1], load_es_bars_csv(sys.argv[2]))
    print(f"Días usables: {len(d)}")
    if len(d):
        pd.set_option("display.width", 220)
        print(evaluate(d).to_string(index=False))
        print(f"\nBarra: p < {P_BAR:.4f} ({N_TESTS} pruebas) Y 3 tercios con el signo previsto. Sin relación aquí = no se pasa a la Etapa 2.")
