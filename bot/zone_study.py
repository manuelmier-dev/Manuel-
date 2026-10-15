"""¿Los walls y los niveles de gamma marcan dónde se hacen el máximo y el mínimo de la primera hora? (contra el azar)

Uso:  python -m bot.zone_study "<carpeta de Theta>" "<barras de ES .csv>" [salida.csv]

Para cada día mide la distancia (en múltiplos del movimiento esperado, EM) entre el máximo/mínimo de la primera hora (9:30-10:30) y cada
nivel candidato calculado ANTES de abrir. Luego repite la medición con niveles "falsos": la posición relativa (nivel - precio)/EM de OTRO día
mezclada al azar. Si los niveles reales no quedan más cerca que los falsos, no aportan información (p-valor alto).
"""
import sys

import numpy as np
import pandas as pd

from .days import build_days
from .journal import load_es_bars_csv
from .loaders import summarize_folder

FH_END = "10:30"
RTH = ("09:30", "15:55")


def day_extremes(bars: pd.DataFrame) -> pd.DataFrame:
    """Máximo y mínimo de la primera hora y del día (sesión regular), con su hora."""
    rows = []
    for d, g in bars.groupby(bars.index.date):
        rth = g.between_time(*RTH)
        fh = rth[rth.index.time < pd.Timestamp(FH_END).time()]
        if len(rth) < 70 or fh.empty or rth.index[0].strftime("%H:%M") != "09:30":
            continue
        rows.append({"date": d, "fh_high": fh["high"].max(), "fh_low": fh["low"].min(), "day_high": rth["high"].max(), "day_low": rth["low"].min(),
                     "high_in_fh": bool(rth["high"].idxmax().time() < pd.Timestamp(FH_END).time()),
                     "low_in_fh": bool(rth["low"].idxmin().time() < pd.Timestamp(FH_END).time())})
    return pd.DataFrame(rows).set_index("date") if rows else pd.DataFrame()


def level_table(summary: pd.DataFrame, days: pd.DataFrame) -> pd.DataFrame:
    """Niveles candidatos en coordenadas ES (strike + base del día), todos conocidos antes de las 9:30."""
    s = summary.assign(date=pd.to_datetime(summary["date"]).dt.date).drop_duplicates("date", keep="last").set_index("date")
    d = days.join(s[["call_wall_gex", "put_wall_gex", "call_wall_oi", "put_wall_oi"]], how="inner")
    b = d["basis"]
    center = d["center_spx"] + b
    return pd.DataFrame({
        "em": d["em_pts"], "center": center, "gex_bn": d["gex_bn"],
        "call_oi_1em": d["call_wall"] + b, "put_oi_1em": d["put_wall"] + b,      # days.call_wall/put_wall vienen en coordenadas SPX: se pasan a ES
        "call_gex": d["call_wall_gex"] + b, "put_gex": d["put_wall_gex"] + b,
        "call_oi_global": d["call_wall_oi"] + b, "put_oi_global": d["put_wall_oi"] + b,
        "mas_1_em": center + d["em_pts"], "menos_1_em": center - d["em_pts"],
    })


def location_stats(ext: pd.Series, level: pd.Series, center: pd.Series, em: pd.Series, n_perm: int = 500, seed: int = 7) -> dict:
    """Distancia mediana |extremo - nivel|/EM contra niveles falsos (posiciones relativas de otros días mezcladas)."""
    k = pd.concat([ext, level, center, em], axis=1, keys=["x", "l", "c", "e"]).dropna()
    k = k[k["e"] > 0]
    if len(k) < 30:
        return {"dias": len(k)}
    d_real = ((k["x"] - k["l"]).abs() / k["e"]).to_numpy()
    off = ((k["l"] - k["c"]) / k["e"]).to_numpy()                  # posición relativa del nivel respecto al precio, en EM
    rng = np.random.default_rng(seed)
    nulls, null_025, null_05 = np.empty(n_perm), np.empty(n_perm), np.empty(n_perm)
    for i in range(n_perm):
        fake = k["c"].to_numpy() + rng.permutation(off) * k["e"].to_numpy()
        d_fake = np.abs(k["x"].to_numpy() - fake) / k["e"].to_numpy()
        nulls[i], null_025[i], null_05[i] = np.median(d_fake), (d_fake <= 0.25).mean(), (d_fake <= 0.5).mean()
    obs = float(np.median(d_real))
    return {"dias": len(k), "mediana_EM": round(obs, 3), "mediana_si_fuera_azar": round(float(nulls.mean()), 3),
            "dentro_0.25EM_%": round(100 * float((d_real <= 0.25).mean()), 1), "azar_0.25EM_%": round(100 * float(null_025.mean()), 1),
            "dentro_0.5EM_%": round(100 * float((d_real <= 0.5).mean()), 1), "azar_0.5EM_%": round(100 * float(null_05.mean()), 1),
            "p_valor": round(float((nulls <= obs).mean()), 3)}


HIGH_LEVELS = ["call_oi_1em", "call_gex", "call_oi_global", "mas_1_em"]
LOW_LEVELS = ["put_oi_1em", "put_gex", "put_oi_global", "menos_1_em"]


def study(levels: pd.DataFrame, ext: pd.DataFrame) -> pd.DataFrame:
    j = levels.join(ext, how="inner")
    rows = []
    for regime, mask in (("todos", j["gex_bn"].notna()), ("gamma_positivo", j["gex_bn"] > 0), ("gamma_negativo", j["gex_bn"] <= 0)):
        g = j[mask]
        for target, col, cands in (("maximo_1a_hora", "fh_high", HIGH_LEVELS), ("minimo_1a_hora", "fh_low", LOW_LEVELS)):
            for lv in cands:
                rows.append({"regimen": regime, "extremo": target, "nivel": lv,
                             **location_stats(g[col], g[lv], g["center"], g["em"])})
    return pd.DataFrame(rows)


if __name__ == "__main__":
    folder, bars_path = sys.argv[1], sys.argv[2]
    out = sys.argv[3] if len(sys.argv) > 3 else "estudio_zonas_primera_hora.csv"
    summary, _ = summarize_folder(folder)
    bars = load_es_bars_csv(bars_path)
    days, _ = build_days(summary, bars, wall_mode="oi_1em")
    ext = day_extremes(bars)
    res = study(level_table(summary, days), ext)
    res.to_csv(out, index=False)
    pd.set_option("display.width", 220)
    print(res.to_string(index=False))
    both = ext.join(days[["gex_bn"]], how="inner")
    print(f"\nDías con extremos: {len(both)}; máximo del día en la 1a hora: {100 * both['high_in_fh'].mean():.0f}%; "
          f"mínimo del día en la 1a hora: {100 * both['low_in_fh'].mean():.0f}%")
    print("p_valor chico (< 0.05) = el nivel real queda más cerca que niveles falsos. Muchos niveles probados: exigir p muy chico y que se repita.")
