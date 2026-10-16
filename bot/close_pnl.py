"""ETAPA 2 de ESTRATEGIA_0DTE_CIERRE.md: ganancia/pérdida REAL (con ask, bid, comisión y deslizamiento) de comprar una opción SPX 0DTE
fuera del dinero en los últimos minutos. Reglas pre-registradas (no se cambian después de ver resultados):
  Entrada 15:30 o 15:45 (al ASK + 0.05), dirección D2 = signo del impulso 15:00 -> entrada. Opera solo si GEX < 0 o rango previo en el tercil alto
  (cortes con días ANTERIORES). Strike OTM más cercano a 0.10% o 0.20% del spot. Filtros: bid>0, ask 0.30-3.00, spread <= min(0.10, 25% ask),
  tamaño del ask >= 5 (si el dato lo trae). Salida A: valor intrínseco al vencimiento. Salida B: vende al BID si vale >=3x la prima a las 15:50
  o a las 15:55 (lo primero), si no, al bid de las 15:55. Comisión 0.65 USD por lado, deslizamiento 0.05 por lado. Multiplicador 100.
  D1 (flujo + impulso) queda PENDIENTE de la descarga de flujo de 15:00-15:45.
16 combinaciones declaradas (D1 y D2 x A/B x 0.10/0.20% x 15:30/15:45): exige p < 0.05/16, los 3 tercios con el mismo signo, >=200 operaciones
y que siga positiva SIN los 5 mejores días. Línea base: comprar call y put OTM todos los días sin señal.
Uso:  python -m bot.close_pnl <carpeta_con_quotes/> <carpeta_theta> <barras_ES.csv>
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from .loaders import _spot_by_parity

NY = "America/New_York"
COMM, SLIP, MULT = 0.65, 0.05, 100.0
N_COMBOS = 16
P_BAR, MIN_TRADES = 0.05 / N_COMBOS, 200
DISTS, ENTRIES, EXITS = (0.0010, 0.0020), ("15:30", "15:45"), ("A", "B")


def wide(q: pd.DataFrame, t: str) -> pd.DataFrame:
    """Cotizaciones del instante t en formato ancho: strike, bid_c, ask_c, ask_size_c, bid_p, ask_p, ask_size_p."""
    s = q[q["t"] == t]
    c, p = s[s["right"] == "C"].set_index("strike"), s[s["right"] == "P"].set_index("strike")
    z = c[["bid", "ask", "ask_size"]].add_suffix("_c").join(p[["bid", "ask", "ask_size"]].add_suffix("_p"), how="outer")
    z["mid_c"], z["mid_p"] = (z["bid_c"] + z["ask_c"]) / 2, (z["bid_p"] + z["ask_p"]) / 2
    return z.reset_index().sort_values("strike").reset_index(drop=True)


def spot_at(z: pd.DataFrame) -> float:
    return _spot_by_parity(z, min_mid=0.5)


def settle_spot(z: pd.DataFrame) -> float:
    """SPX al vencimiento a partir de las opciones muy dentro del dinero a las 15:59:59 (call ITM vale ~ S-K; put ITM vale ~ K-S)."""
    calls = z[(z["mid_c"] >= 0.5) & (z["mid_p"].fillna(9) <= 0.10)].tail(3)
    puts = z[(z["mid_p"] >= 0.5) & (z["mid_c"].fillna(9) <= 0.10)].head(3)
    est = list(calls["strike"] + calls["mid_c"]) + list(puts["strike"] - puts["mid_p"])
    return float(np.median(est)) if est else float("nan")


def pick_contract(z: pd.DataFrame, spot: float, side: int, dist: float) -> dict | None:
    """side +1 = call, -1 = put. Devuelve el strike OTM más cercano al objetivo que cumpla los filtros."""
    r, other = ("c", "p") if side > 0 else ("p", "c")
    target = spot * (1 + side * dist)
    ok = z.dropna(subset=[f"bid_{r}", f"ask_{r}"])
    ok = ok[(ok["strike"] * side > spot * side) & (ok[f"bid_{r}"] > 0) & (ok[f"ask_{r}"].between(0.30, 3.00))]
    ok = ok[(ok[f"ask_{r}"] - ok[f"bid_{r}"]) <= np.minimum(0.10, 0.25 * ok[f"ask_{r}"])]
    sz = ok[f"ask_size_{r}"]
    ok = ok[sz.isna() | (sz >= 5)]
    if ok.empty:
        return None
    row = ok.iloc[(ok["strike"] - target).abs().argmin()]
    return {"strike": float(row["strike"]), "ask": float(row[f"ask_{r}"]), "side": side}


def trade_pnl(q: pd.DataFrame, entry: str, side: int, dist: float, exit_mode: str) -> dict | None:
    ze = wide(q, entry + ":00")
    if ze.empty:
        return None
    spot = spot_at(ze)
    k = pick_contract(ze, spot, side, dist)
    if k is None:
        return None
    cost = (k["ask"] + SLIP) * MULT + COMM
    r = "c" if side > 0 else "p"
    if exit_mode == "A":
        s_end = settle_spot(wide(q, "15:59:59"))
        if np.isnan(s_end):
            return None
        value = max(side * (s_end - k["strike"]), 0.0) * MULT - COMM
    else:
        value = None
        for t in ("15:50:00", "15:55:00"):
            zt = wide(q, t)
            row = zt[zt["strike"] == k["strike"]]
            if row.empty or pd.isna(row[f"bid_{r}"].iloc[0]):
                continue
            bid = float(row[f"bid_{r}"].iloc[0])
            if bid >= 3 * k["ask"] or t == "15:55:00":
                value = max(bid - SLIP, 0.0) * MULT - COMM
                break
        if value is None:
            return None
    return {"cost": cost, "pnl": value - cost, "premium": k["ask"], "strike": k["strike"]}


def pre_entry(bars: pd.DataFrame, day, entry: str) -> dict | None:
    """Solo barras ya cerradas al momento de entrar (inicio < entrada)."""
    d = pd.Timestamp(day).date()
    t0, t1 = pd.Timestamp(f"{d} 15:00", tz=NY), pd.Timestamp(f"{d} {entry}", tz=NY) - pd.Timedelta(minutes=5)
    a = bars.loc[t0:t1]
    if len(a) < 4:
        return None
    return {"imp": float(a["close"].iloc[-1] - a["open"].iloc[0]), "rng": float(a["high"].max() - a["low"].min())}


def summarize(pnl: np.ndarray, dates: np.ndarray, placebo: np.ndarray | None = None) -> dict:
    n = len(pnl)
    out = {"n": n, "usd_prom": float(pnl.mean()) if n else np.nan, "usd_mediana": float(np.median(pnl)) if n else np.nan,
           "pct_gana": float((pnl > 0).mean()) if n else np.nan}
    if n >= 10:
        rng = np.random.default_rng(5)
        boot = np.array([rng.choice(pnl, n).mean() for _ in range(2000)])
        out["ic95"] = f"{np.percentile(boot, 2.5):+.0f} a {np.percentile(boot, 97.5):+.0f}"
        out["sin_top5"] = float(np.sort(pnl)[:-5].mean()) if n > 5 else np.nan
        out["tercios"] = " | ".join(f"{p.mean():+.0f}" for p in np.array_split(pnl[np.argsort(dates)], 3))
    return out


def run_rules(daily: pd.DataFrame, n_placebo: int = 2000, seed: int = 9) -> pd.DataFrame:
    """daily: una fila por día y combinación: date, entry, dist, exit, side(+1/-1 de la regla), pnl_regla, pnl_opuesto (dirección contraria)."""
    rng, rows = np.random.default_rng(seed), []
    for (entry, dist, ex), g in daily.groupby(["entry", "dist", "exit"]):
        g = g.dropna(subset=["pnl_regla"])
        s = summarize(g["pnl_regla"].to_numpy(), g["date"].to_numpy(dtype="datetime64[ns]"))
        both = g.dropna(subset=["pnl_opuesto"])
        if len(both) >= 10:      # placebo: dirección al azar entre la de la regla y la contraria, mismos días
            pick = rng.integers(0, 2, (n_placebo, len(both)))
            sims = np.where(pick == 1, both["pnl_regla"].to_numpy(), both["pnl_opuesto"].to_numpy()).mean(axis=1)
            s["p_azar"] = float((sims >= both["pnl_regla"].mean()).mean())
        ok = (s["n"] >= MIN_TRADES and s.get("p_azar", 1) < P_BAR and s.get("sin_top5", -1) > 0
              and all(float(x) > 0 for x in s.get("tercios", "-1").replace(" ", "").split("|")))
        rows.append({"regla": "D2", "entrada": entry, "dist_%": dist * 100, "salida": ex, **s, "veredicto": "CANDIDATA" if ok else "SIN VENTAJA"})
    return pd.DataFrame(rows)


def baseline(quotes_dir, entry="15:45", dist=0.0020, exit_mode="A") -> dict:
    """Comprar SIEMPRE un call y un put OTM sin señal. Se espera negativa."""
    pn, dates = [], []
    for f in sorted(Path(quotes_dir).glob("*.csv")):
        q = pd.read_csv(f)
        for side in (1, -1):
            t = trade_pnl(q, entry, side, dist, exit_mode)
            if t:
                pn.append(t["pnl"])
                dates.append(pd.Timestamp(f.stem).to_datetime64())
    return summarize(np.array(pn), np.array(dates))


def build_daily(quotes_dir, features: pd.DataFrame, bars: pd.DataFrame) -> pd.DataFrame:
    """features: índice fecha, columnas gex_bn y (opcional) nada más. S3 tercil alto con cortes de días anteriores."""
    rows, hist_rng = [], {e: [] for e in ENTRIES}
    for f in sorted(Path(quotes_dir).glob("*.csv")):
        d = pd.Timestamp(f.stem)
        if d not in features.index:
            continue
        q = pd.read_csv(f)
        for e in ENTRIES:
            pe = pre_entry(bars, d, e)
            if pe is None:
                continue
            past = hist_rng[e]
            top = len(past) >= 60 and pe["rng"] > np.percentile(past, 66.7)
            past.append(pe["rng"])
            if not (features.loc[d, "gex_bn"] < 0 or top) or pe["imp"] == 0:
                continue
            side = 1 if pe["imp"] > 0 else -1
            for dist in DISTS:
                for ex in EXITS:
                    a, b = trade_pnl(q, e, side, dist, ex), trade_pnl(q, e, -side, dist, ex)
                    rows.append({"date": d, "entry": e, "dist": dist, "exit": ex, "pnl_regla": a["pnl"] if a else np.nan,
                                 "pnl_opuesto": b["pnl"] if b else np.nan})
    return pd.DataFrame(rows)


if __name__ == "__main__":
    from .days import build_days
    from .journal import load_es_bars_csv
    from .loaders import summarize_folder
    quotes_dir, theta, bars_path = sys.argv[1:4]
    bars = load_es_bars_csv(bars_path)
    summary, _ = summarize_folder(theta)
    days, _ = build_days(summary, bars)
    days.index = pd.to_datetime(days.index)
    daily = build_daily(quotes_dir, days, bars)
    pd.set_option("display.width", 250)
    print(f"Días con cotizaciones: {len(list(Path(quotes_dir).glob('*.csv')))}; filas de operaciones simuladas: {len(daily)}")
    if len(daily):
        print(run_rules(daily).to_string(index=False))
    print("\nLÍNEA BASE (call y put OTM cada día, 15:45, 0.20%, vence): ", baseline(quotes_dir))
    print(f"Barra: p < {P_BAR:.4f} ({N_COMBOS} combinaciones), >= {MIN_TRADES} operaciones, 3 tercios positivos y positiva sin los 5 mejores días. D1 pendiente.")
