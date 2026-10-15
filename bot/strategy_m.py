"""Estrategia de don Manuel (15-oct-2026): compra de reversión en pre-mercado con MACD (histograma), RSI y VWAP con bandas. Solo ES, sin opciones.

Uso:  python -m bot.strategy_m <barras1.csv> [<barras2.csv> ...] [--sens] [--instrumento ES|NQ|YM|RTY]

Reglas tal como las dio don Manuel + SUPUESTOS (marcados) para lo que no dijo. Todo fijado antes de ver resultados:
  Gráfica de 5 minutos, ES 24 horas. MACD (12, 26, 9) en histograma, RSI (14), VWAP de la sesión Globex (reinicia 18:00 NY) con bandas de +-2 desviaciones.
  ENTRADA (compra): ventana = de 7:30 a 10:30 NY (2 horas antes de la apertura americana y hasta el final de la primera hora; correcciones de don Manuel,
     15-oct). [SUPUESTO: horas de Nueva York; la última barra con entrada posible es la de 10:25]. UNA sola operación al día. Al CIERRE de una barra se cumple:
     - RSI de la barra anterior < 33 y el RSI sube respecto a esa barra ("después de llegar a menos de 33")        [SUPUESTO: "llegar" = la barra anterior]
     - cierre por debajo de la banda baja del VWAP y la barra sube (cierre > apertura)
     - MACD: modo A (literal): histograma MENOR que el de la barra anterior;  modo B (alternativa): histograma MAYOR (se acorta si es rojo)
     Entra a mercado en la APERTURA de la siguiente barra [SUPUESTO: no se puede ver "dentro de la barra" con datos de 5 min]. Una sola operación al día (indicado por don Manuel).
  SALIDA: al cierre de una barra se cumplen TODAS: banda alta del VWAP subiendo, el precio la cruza hacia abajo (cierre anterior >= banda, cierre actual < banda),
     MACD en verde (histograma > 0) y menor que el de la barra anterior, RSI bajando y por debajo de 70. Sale a mercado en la apertura de la siguiente barra.
     [SUPUESTO: salida de seguridad a las 15:55 NY, sin stop de pérdida porque no lo pidió.]
  Costo: 29 USD por operación (0.58 pts). 1 contrato.
Se compara contra un PLACEBO: la misma cantidad de días con entrada en una barra al azar de la misma ventana y la misma duración de la operación.
"""
import sys

import numpy as np
import pandas as pd

from .hyp_test import COST_PTS as ES_COST_PTS
from .indicators import rsi
from .journal import load_es_bars_csv

NY = "America/New_York"
# (valor de 1 punto en USD, tamaño de 1 tick en puntos). Costo por operación = comisión 4 USD + 1 tick de deslizamiento por lado (ES: 29 USD).
INSTRUMENTS = {"ES": (50.0, 0.25), "NQ": (20.0, 0.25), "YM": (5.0, 1.0), "RTY": (50.0, 0.10)}


def costs(instrument: str = "ES") -> tuple[float, float]:
    """(costo en puntos, valor del punto) del instrumento."""
    pv, tick = INSTRUMENTS[instrument]
    return (4.0 + 2 * tick * pv) / pv, pv

WIN_START, WIN_END = "07:30", "10:30"          # barras de ENTRADA: inicio >= 7:30 y < 10:30
FLAT = "15:55"


def add_manuel_indicators(bars: pd.DataFrame) -> pd.DataFrame:
    df = bars.copy()
    c = df["close"]
    macd = c.ewm(span=12, adjust=False).mean() - c.ewm(span=26, adjust=False).mean()
    df["hist"] = macd - macd.ewm(span=9, adjust=False).mean()
    df["rsi"] = rsi(c, 14)
    sess = (df.index - pd.Timedelta(hours=18)).date                      # la sesión Globex empieza a las 18:00 NY del día anterior
    g = pd.Series(sess, index=df.index)
    tp = (df["high"] + df["low"] + df["close"]) / 3
    v = df["volume"].astype(float)
    cv = v.groupby(g).cumsum().replace(0, np.nan)
    vwap = (tp * v).groupby(g).cumsum() / cv
    sd = np.sqrt((((tp**2) * v).groupby(g).cumsum() / cv - vwap**2).clip(lower=0))
    df["vwap"], df["vwap_up"], df["vwap_dn"], df["vwap_sd"] = vwap, vwap + 2 * sd, vwap - 2 * sd, sd
    return df


def signals(df: pd.DataFrame, mode: str = "A", rsi_th: float = 33.0, band_k: float = 2.0) -> pd.DataFrame:
    """mode: "A" (histograma menor), "B" (histograma mayor) o "N" (sin condición de MACD). rsi_th y band_k solo se cambian en la tabla de sensibilidad."""
    h, hp = df["hist"], df["hist"].shift(1)
    r, rp = df["rsi"], df["rsi"].shift(1)
    macd_ok = (h < hp) if mode == "A" else (h > hp) if mode == "B" else pd.Series(True, index=df.index)
    below = df["close"] < (df["vwap"] - band_k * df["vwap_sd"]) if band_k != 2.0 else df["close"] < df["vwap_dn"]
    entry = (rp < rsi_th) & (r > rp) & below & (df["close"] > df["open"]) & macd_ok
    up, upp, cp = df["vwap_up"], df["vwap_up"].shift(1), df["close"].shift(1)
    exit_ = (up > upp) & (cp >= upp) & (df["close"] < up) & (h > 0) & (h < hp) & (r < rp) & (r < 70)
    return pd.DataFrame({"entry": entry.fillna(False), "exit": exit_.fillna(False)})


def _hm(s: str) -> int:
    return int(s[:2]) * 60 + int(s[3:])


def run(df: pd.DataFrame, sig: pd.DataFrame, multi: bool = False, win_start: str = WIN_START, win_end: str = WIN_END,
        exit_mode: str = "regla") -> pd.DataFrame:
    """Entradas en la ventana; sale por la regla o a las 15:55. Una por día (multi=False) o varias, una posición a la vez (multi=True).
    exit_mode: "regla" (la salida original con MACD+RSI+VWAP), "X1" (la primera barra bajista que cierra debajo de la banda alta del VWAP) o
    "X2" (igual, pero solo después de que el precio tocó la banda alta desde la entrada: un rechazo). Devuelve las operaciones (en puntos, sin costos)."""
    t = df.index
    mins = np.array(t.hour * 60 + t.minute)
    day = np.array(t.date)
    o, c, hi, up = df["open"].to_numpy(), df["close"].to_numpy(), df["high"].to_numpy(), df["vwap_up"].to_numpy()
    e_arr, x_arr = sig["entry"].to_numpy(), sig["exit"].to_numpy()
    bear_below = (c < o) & (c < up)                           # barra bajista que cierra debajo de la banda alta del VWAP
    w0, w1, fl = _hm(win_start), _hm(win_end), 15 * 60 + 55
    n = len(df)
    trades, last_day, busy_until = [], None, -1
    for i in np.flatnonzero(e_arr):
        j = i + 1                                             # entrada en la apertura de la barra siguiente
        if j >= n or (t[j] - t[i]) != pd.Timedelta(minutes=5) or day[j] != day[i]:
            continue
        if not (w0 <= mins[j] < w1) or j <= busy_until:
            continue
        if not multi and day[j] == last_day:
            continue
        last_day = day[j]
        k, touched = j, False
        while True:                                           # recorre barras del mismo día
            if mins[k] >= fl or k + 1 >= n or day[k + 1] != day[k]:
                xp, why, kx = c[k], "hora", k
                break
            touched = touched or bool(hi[k] >= up[k])           # (solo se usa en X2)
            if exit_mode == "regla":
                hit = bool(x_arr[k])
            elif exit_mode == "X1":
                hit = bool(bear_below[k])
            else:
                hit = touched and bool(bear_below[k])
            if hit:
                xp, why, kx = o[k + 1], "regla", k + 1
                break
            k += 1
        busy_until = kx
        trades.append({"date": day[j], "entry_time": t[j], "exit_time": t[kx], "entry": o[j], "exit": xp, "pts": xp - o[j], "motivo": why, "barras": kx - j})
    return pd.DataFrame(trades)


def placebo(df: pd.DataFrame, trades: pd.DataFrame, n_perm: int = 500, seed: int = 9, win_start: str = WIN_START, win_end: str = WIN_END) -> dict:
    """Misma cantidad de días, entrada en una barra al azar de la ventana, misma duración. ¿La regla gana más que entrar al azar?"""
    rng = np.random.default_rng(seed)
    t = df.index
    mins = np.array(t.hour * 60 + t.minute)
    day = np.array(t.date)
    o, c = df["open"].to_numpy(), df["close"].to_numpy()
    cand = {}
    for i in np.flatnonzero((mins >= _hm(win_start)) & (mins < _hm(win_end))):
        cand.setdefault(day[i], []).append(i)
    rows = []
    for _, tr in trades.iterrows():
        idxs = cand.get(tr["date"])
        if idxs:
            rows.append((np.array(idxs), int(tr["barras"])))
    means = np.empty(n_perm)
    for p in range(n_perm):
        x = []
        for idxs, dur in rows:
            j = int(rng.choice(idxs))
            k = min(j + dur, len(df) - 1)
            x.append(c[k] - o[j] if day[k] == day[j] else np.nan)
        means[p] = np.nanmean(x)
    real = float(trades["pts"].mean())
    return {"placebo_pts_promedio": round(float(means.mean()), 2), "p_valor": round(float((means >= real).mean()), 4)}


def stats(tr: pd.DataFrame, instrument: str = "ES") -> dict:
    if len(tr) < 5:
        return {"n": len(tr)}
    cost_pts, pv = costs(instrument)
    net = tr["pts"] - cost_pts
    eq = (net * pv).cumsum()
    return {"n": len(tr), "pts_bruto": round(tr["pts"].mean(), 2), "pts_neto": round(net.mean(), 2),
            "t_neto": round(net.mean() / (net.std(ddof=1) / np.sqrt(len(net))), 2) if len(net) > 2 and net.std(ddof=1) > 0 else np.nan,
            "aciertos_%": round(100 * (net > 0).mean(), 1), "total_usd_neto": round(net.sum() * pv, 0),
            "peor_caida_usd": round(float((eq - eq.cummax()).min()), 0), "salen_por_regla_%": round(100 * (tr["motivo"] == "regla").mean(), 1),
            "barras_promedio": round(tr["barras"].mean(), 1)}


def sensitivity(df: pd.DataFrame, instrument: str = "ES") -> pd.DataFrame:
    """Cuán amplio es el efecto: variar el umbral de RSI, la banda del VWAP y la condición de MACD. DIAGNÓSTICO, no para elegir la mejor."""
    rows = []
    for rsi_th in (30.0, 33.0, 38.0, 42.0):
        for band_k in (2.0, 1.0):
            for mode in ("A", "B", "N"):
                tr = run(df, signals(df, mode, rsi_th, band_k))
                st = stats(tr, instrument)
                pl = placebo(df, tr, n_perm=300)["p_valor"] if len(tr) >= 20 else np.nan
                rows.append({"rsi<": rsi_th, "banda_sigma": band_k, "macd": mode, **{k: st.get(k) for k in ("n", "pts_neto", "t_neto", "aciertos_%", "total_usd_neto", "peor_caida_usd")}, "p_placebo": pl})
    return pd.DataFrame(rows)


if __name__ == "__main__":
    instrument = sys.argv[sys.argv.index("--instrumento") + 1] if "--instrumento" in sys.argv else "ES"
    paths = [a for i, a in enumerate(sys.argv[1:], 1) if not a.startswith("--") and sys.argv[i - 1] != "--instrumento"]
    parts = [load_es_bars_csv(p) for p in paths]
    bars = pd.concat(parts).sort_index()
    bars = bars[~bars.index.duplicated(keep="last")]
    print(f"Barras: {len(bars)}  ({bars.index[0]:%Y-%m-%d} a {bars.index[-1]:%Y-%m-%d})")
    df = add_manuel_indicators(bars)
    pd.set_option("display.width", 220)
    if "--sens" in sys.argv:
        print(f"Instrumento: {instrument} (costo {costs(instrument)[0]:.2f} pts = {costs(instrument)[0] * costs(instrument)[1]:.0f} USD por operación)")
        print(sensitivity(df, instrument).to_string(index=False))
        print("\nSi el efecto es real debería verse en muchas filas (no solo en una) y con más operaciones al aflojar las reglas. 'N' = sin MACD.")
        sys.exit(0)
    rows = []
    for mode, text in (("A", "MACD menor"), ("B", "MACD mayor"), ("N", "sin MACD")):
        for ex, extext in (("X1", "primera barra bajista bajo la banda alta"), ("X2", "barra bajista bajo la banda alta tras TOCARLA")):
            tr = run(df, signals(df, mode), exit_mode=ex)
            st = stats(tr, instrument)
            rows.append({"entrada": f"{mode} ({text})", "salida": f"{ex} ({extext})", **{k: st.get(k) for k in ("n", "pts_neto", "t_neto", "aciertos_%", "total_usd_neto", "peor_caida_usd", "salen_por_regla_%", "barras_promedio")},
                         "p_placebo": placebo(df, tr)["p_valor"] if len(tr) >= 20 else np.nan})
            if len(tr) >= 5 and (mode == "N" or (mode == "B" and ex == "X2")):
                yr = pd.to_datetime(tr["date"]).dt.year
                rows[-1]["_por_anio"] = pd.DataFrame({int(y): stats(g, instrument) for y, g in tr.groupby(yr)}).T.to_string()
    print(f"Instrumento: {instrument} (costo {costs(instrument)[0]:.2f} pts = {costs(instrument)[0] * costs(instrument)[1]:.0f} USD por operación)")
    print(pd.DataFrame([{k: v for k, v in r.items() if k != "_por_anio"} for r in rows]).to_string(index=False))
    for r in rows:
        if "_por_anio" in r:
            print(f"\nPor año: entrada {r['entrada']} / salida {r['salida']}")
            print(r["_por_anio"])
    print("\n--- Salida ORIGINAL (MACD + RSI + VWAP, para comparar) ---")
    for mode in ("A", "B", "N"):
        print(mode, stats(run(df, signals(df, mode)), instrument))
    print("\nSe aprueba solo si el neto es positivo, t > 2, p < 0.008 (0.05 / 6 variantes) contra el placebo y el signo se repite en la mayoría de los años.")
