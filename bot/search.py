"""Búsqueda HONESTA de patrones de entrada y salida en ES (y réplica en otros índices), con candados contra el autoengaño.

Uso:  python -m bot.search --es <barras1.csv> [<barras2.csv> ...] [--otros NQ=<csv> YM=<csv> RTY=<csv>] [--nulos 30]

Qué hace: define de antemano un espacio finito de reglas simples (una operación al día como máximo):
  ENTRADA = (hora de decisión) x (condición sobre una variable conocida en ese momento) x (largo o corto)
     horas 7:30, 8:30, 9:30, 10:00, 10:30, 12:00, 14:00, 15:30 NY; variables: desvío del precio contra el VWAP Globex (en sigmas), RSI, hueco nocturno,
     rendimiento desde la apertura, rendimiento del día anterior, ruptura del máximo/mínimo de ayer, ruptura del rango de los primeros 30 minutos, día de la semana.
  SALIDA  = tiempo fijo (15 min, 30 min, 1 h, 2 h, 4 h, cierre 15:55) o stop/objetivo en múltiplos del rango diario medio (ATR), siempre con cierre a las 15:55.
Candados:
  1. Se elige con 2010-2018 (entrenamiento), se confirma con 2019-2022 (validación) y se prueba UNA vez en 2023-2026 y en otros índices.
  2. El mismo procedimiento se repite 30 veces con los rendimientos MEZCLADOS entre días (sin relación real con las condiciones): eso dice cuánto "gana" el
     mejor patrón solo por suerte y cuántos pasan la validación sin tener nada real.
  3. Costos incluidos (29 USD por operación en ES). Criterio final fijado antes: neto positivo y t > 2 en la prueba 2023-26 y neto positivo en al menos 2 de 3 índices.
"""
import os
import sys

import numpy as np
import pandas as pd

from .journal import load_es_bars_csv
from .strategy_m import add_manuel_indicators, costs

NY = "America/New_York"
TIMES = ["07:30", "08:30", "09:30", "10:00", "10:30", "12:00", "14:00", "15:30"]
HORIZONS = {"15m": 3, "30m": 6, "1h": 12, "2h": 24, "4h": 48, "cierre": None}
STOP_TARGET = [(0.1, 0.2), (0.1, 0.4), (0.2, 0.2), (0.2, 0.4), (0.2, 0.8), (0.35, 0.35), (0.35, 0.7)]        # (stop, objetivo) en múltiplos del ATR
EXITS = list(HORIZONS) + [f"S{s}/T{t}" for s, t in STOP_TARGET]
TRAIN_END, VAL_END = pd.Timestamp("2019-01-01"), pd.Timestamp("2023-01-01")


def _hm(s: str) -> int:
    return int(s[:2]) * 60 + int(s[3:])


def daily_frame(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for d, g in df.groupby(df.index.date):
        rth = g.between_time("09:30", "15:55")
        if len(rth) < 70 or rth.index[0].strftime("%H:%M") != "09:30" or rth.index[-1].strftime("%H:%M") != "15:55":
            continue
        first = rth.iloc[:6]                                              # primeros 30 minutos (9:30 a 9:55)
        rows.append({"date": pd.Timestamp(d), "open": rth["open"].iloc[0], "close": rth["close"].iloc[-1], "high": rth["high"].max(), "low": rth["low"].min(),
                     "or_high": first["high"].max(), "or_low": first["low"].min()})
    t = pd.DataFrame(rows).set_index("date")
    t["atr"] = (t["high"] - t["low"]).shift(1).rolling(20).mean()
    t["prev_close"], t["prev_high"], t["prev_low"] = t["close"].shift(1), t["high"].shift(1), t["low"].shift(1)
    t["prev_ret"] = t["close"].shift(1) - t["close"].shift(2)
    return t


def build(df: pd.DataFrame) -> dict:
    """Matrices por hora de decisión: variables (conocidas ANTES de entrar) y resultados de cada salida, para largo y corto."""
    day = daily_frame(df)
    o, h, l, c = (df[k].to_numpy() for k in ("open", "high", "low", "close"))
    vw, sd, rsi = df["vwap"].to_numpy(), df["vwap_sd"].to_numpy(), df["rsi"].to_numpy()
    out = {"days": day.index, "T": {}}
    for T in TIMES:
        targets = pd.DatetimeIndex([pd.Timestamp(f"{d.date()} {T}", tz=NY) for d in day.index])
        j = df.index.get_indexer(targets)
        endt = pd.DatetimeIndex([pd.Timestamp(f"{d.date()} 15:55", tz=NY) for d in day.index])
        e = df.index.get_indexer(endt)
        ok = (j >= 1) & (e > j)
        ok[ok] &= (df.index[j[ok] - 1] == targets[ok] - pd.Timedelta(minutes=5))              # la barra anterior existe y es la de 5 minutos antes
        jj = np.where(ok, j, 0)
        ee = np.where(ok, e, 0)
        width = int((ee - jj).max()) + 1
        pos = np.minimum(jj[:, None] + np.arange(width)[None, :], ee[:, None])
        valid = (jj[:, None] + np.arange(width)[None, :]) <= ee[:, None]
        entry = o[jj]
        H = np.where(valid, h[pos] - entry[:, None], np.nan)
        L = np.where(valid, l[pos] - entry[:, None], np.nan)
        C = c[pos] - entry[:, None]                                                          # cierres (repite el último después del final)
        atr = day["atr"].to_numpy()
        last = c[ee] - entry
        res = {}
        for name, k in HORIZONS.items():
            kk = np.minimum((k - 1) if k else width, ee - jj)
            val = np.take_along_axis(C, kk[:, None], axis=1)[:, 0]
            res[(name, "L")], res[(name, "S")] = val, -val
        for s_m, t_m in STOP_TARGET:
            s_, g_ = s_m * atr, t_m * atr
            for side in ("L", "S"):
                hit_stop = (L <= -s_[:, None]) if side == "L" else (H >= s_[:, None])
                hit_tgt = (H >= g_[:, None]) if side == "L" else (L <= -g_[:, None])
                i_stop = np.where(hit_stop.any(axis=1), hit_stop.argmax(axis=1), 10**6)
                i_tgt = np.where(hit_tgt.any(axis=1), hit_tgt.argmax(axis=1), 10**6)
                pnl = np.where(i_stop <= i_tgt, np.where(i_stop < 10**6, -s_, (last if side == "L" else -last)), g_)     # empate en la misma barra: primero el stop
                res[(f"S{s_m}/T{t_m}", side)] = pnl
        # variables
        prev = day["prev_close"].to_numpy()
        cl1 = c[np.maximum(jj - 1, 0)]
        early = _hm(T) < 9 * 60 + 30
        feats = {
            "vwapz": np.where(sd[np.maximum(jj - 1, 0)] > 0, (cl1 - vw[np.maximum(jj - 1, 0)]) / sd[np.maximum(jj - 1, 0)], np.nan),
            "rsi": rsi[np.maximum(jj - 1, 0)],
            "gap": ((cl1 if early else day["open"].to_numpy()) - prev) / atr,
            "ret_open": np.full(len(day), np.nan) if _hm(T) < 10 * 60 else (cl1 - day["open"].to_numpy()) / atr,
            "prev_ret": day["prev_ret"].to_numpy() / atr,
            "dist_pdh": (cl1 - day["prev_high"].to_numpy()) / atr,
            "dist_pdl": (day["prev_low"].to_numpy() - cl1) / atr,
            "orb_up": np.full(len(day), np.nan) if _hm(T) < 10 * 60 + 30 else (cl1 > day["or_high"].to_numpy()).astype(float),
            "orb_dn": np.full(len(day), np.nan) if _hm(T) < 10 * 60 + 30 else (cl1 < day["or_low"].to_numpy()).astype(float),
            "dow": np.array([d.weekday() for d in day.index], dtype=float),
        }
        out["T"][T] = {"ok": ok, "res": res, "feats": feats}
    out["atr"] = day["atr"].to_numpy()
    return out


def masks_for(T_data: dict) -> dict:
    f, ok = T_data["feats"], T_data["ok"]
    m = {}
    for k in (1.5, 2.0, 2.5, 3.0):
        m[f"vwapz<=-{k}"], m[f"vwapz>={k}"] = f["vwapz"] <= -k, f["vwapz"] >= k
    for k in (30, 25, 20):
        m[f"rsi<={k}"] = f["rsi"] <= k
    for k in (70, 75, 80):
        m[f"rsi>={k}"] = f["rsi"] >= k
    for name, grid in (("gap", (0.1, 0.25, 0.5)), ("ret_open", (0.15, 0.3, 0.6)), ("prev_ret", (0.3, 0.6, 1.0))):
        for k in grid:
            m[f"{name}<=-{k}"], m[f"{name}>={k}"] = f[name] <= -k, f[name] >= k
    m["rompe_max_ayer"], m["rompe_min_ayer"] = f["dist_pdh"] >= 0.1, f["dist_pdl"] >= 0.1
    m["rompe_rango30_arriba"], m["rompe_rango30_abajo"] = f["orb_up"] == 1, f["orb_dn"] == 1
    for dw in range(5):
        m[f"dia_{dw}"] = f["dow"] == dw
    return {k: np.asarray(v) & ok & np.isfinite(T_data["res"][("cierre", "L")]) for k, v in m.items()}


def stat(ret: np.ndarray, mask: np.ndarray, cost: float) -> tuple[int, float, float]:
    x = ret[mask & np.isfinite(ret)] - cost
    n = len(x)
    if n < 5 or x.std(ddof=1) == 0:
        return n, np.nan, np.nan
    return n, float(x.mean()), float(x.mean() / (x.std(ddof=1) / np.sqrt(n)))


def search(data: dict, cost: float, perm: np.ndarray | None = None, min_train: int = 80, min_val: int = 25) -> pd.DataFrame:
    days = data["days"]
    train, val, test = days < TRAIN_END, (days >= TRAIN_END) & (days < VAL_END), days >= VAL_END
    rows = []
    for T, td in data["T"].items():
        masks = masks_for(td)
        for (exit_name, side), ret in td["res"].items():
            r = ret if perm is None else ret[perm]
            for mname, mk in masks.items():
                n1, m1, t1 = stat(r, mk & train, cost)
                if n1 < min_train or not np.isfinite(t1):
                    continue
                n2, m2, t2 = stat(r, mk & val, cost)
                n3, m3, t3 = stat(r, mk & test, cost)
                rows.append({"T": T, "condicion": mname, "lado": "largo" if side == "L" else "corto", "salida": exit_name, "n_train": n1, "neto_train": m1, "t_train": t1,
                             "n_val": n2, "neto_val": m2, "t_val": t2, "n_test": n3, "neto_test": m3, "t_test": t3})
    return pd.DataFrame(rows)


def pick(res: pd.DataFrame, top: int = 30) -> pd.DataFrame:
    """Candidatas: las `top` de mayor t en entrenamiento que además se confirman en validación (neto > 0 y t > 1.64) con al menos min_val operaciones."""
    best = res.sort_values("t_train", ascending=False).head(top)
    return best[(best["neto_val"] > 0) & (best["t_val"] > 1.64) & (best["n_val"] >= 25)]


def null_runs(data: dict, cost: float, n: int, seed: int = 1) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for _ in range(n):
        perm = rng.permutation(len(data["days"]))
        r = search(data, cost, perm)
        rows.append({"mejor_t_train": r["t_train"].max(), "pasan_validacion": len(pick(r))})
    return pd.DataFrame(rows)


def load(paths) -> pd.DataFrame:
    bars = pd.concat([load_es_bars_csv(p) for p in paths]).sort_index()
    return add_manuel_indicators(bars[~bars.index.duplicated(keep="last")])


def apply_variants(data: dict, picks: pd.DataFrame, cost: float) -> pd.DataFrame:
    rows = []
    for _, p in picks.iterrows():
        td = data["T"][p["T"]]
        ret = td["res"][(p["salida"], "L" if p["lado"] == "largo" else "S")]
        mk = masks_for(td)[p["condicion"]]
        n, m, t = stat(ret, mk, cost)
        n2, m2, t2 = stat(ret, mk & (data["days"] >= VAL_END), cost)
        rows.append({"T": p["T"], "condicion": p["condicion"], "lado": p["lado"], "salida": p["salida"], "n_total": n, "neto_total": m, "t_total": t, "n_2023_26": n2, "neto_2023_26": m2, "t_2023_26": t2})
    return pd.DataFrame(rows)


if __name__ == "__main__":
    args = sys.argv[1:]
    es_paths = args[args.index("--es") + 1:]
    es_paths = [p for p in es_paths[: next((i for i, a in enumerate(es_paths) if a.startswith("--")), len(es_paths))]]
    others = {}
    if "--otros" in args:
        for a in args[args.index("--otros") + 1:]:
            if a.startswith("--"):
                break
            k, v = a.split("=")
            others[k] = v
    n_null = int(args[args.index("--nulos") + 1]) if "--nulos" in args else 30
    pd.set_option("display.width", 250)
    cost_es = costs("ES")[0]
    print("Cargando ES y calculando matrices...")
    data = build(load(es_paths))
    res = search(data, cost_es)
    print(f"\nVariantes evaluadas (con operaciones suficientes en entrenamiento): {len(res)}")
    print("\n== Las 15 mejores en ENTRENAMIENTO (2010-2018) y qué pasó después ==")
    print(res.sort_values("t_train", ascending=False).head(15).round(2).to_string(index=False))
    chosen = pick(res)
    print(f"\n== Candidatas que también se confirman en VALIDACIÓN (2019-2022): {len(chosen)} ==")
    if len(chosen):
        print(chosen.round(2).to_string(index=False))
    print(f"\n== Mismo procedimiento con rendimientos MEZCLADOS ({n_null} veces): lo que se obtiene solo por suerte ==")
    nl = null_runs(data, cost_es, n_null)
    print(f"Mejor t en entrenamiento por pura suerte: promedio {nl['mejor_t_train'].mean():.2f}, máximo {nl['mejor_t_train'].max():.2f}   (real: {res['t_train'].max():.2f})")
    print(f"Candidatas que pasan validación por pura suerte: promedio {nl['pasan_validacion'].mean():.1f}, máximo {nl['pasan_validacion'].max()}   (real: {len(chosen)})")
    if len(chosen):
        final = apply_variants(data, chosen, cost_es)
        print("\n== PRUEBA FINAL, ES: todo el periodo y 2023-2026 (nunca se usó para elegir) ==")
        print(final.round(2).to_string(index=False))
        for name, path in others.items():
            if not os.path.exists(path):
                print(f"\n== RÉPLICA en {name}: no existe {path} (todavía no se descargó) ==")
                continue
            print(f"\n== RÉPLICA en {name} (costos propios) ==")
            d2 = build(load([path]))
            print(apply_variants(d2, chosen, costs(name)[0]).round(2).to_string(index=False))
    print("\nCriterio fijado de antemano: una candidata solo vale si en 2023-26 tiene neto > 0 y t > 2, y es positiva en al menos 2 de 3 índices; y si el número de candidatas reales no supera claramente al de la suerte.")
