"""Gráficas de estudio: cada día con las zonas, las señales y las decisiones del bot, para ver CÓMO decide.

Marcas (todas con "x"):
  x azul grande     el máximo y el mínimo reales del día (con su hora; se indica si cayeron en la primera hora)
  x gris pequeña    una barra que toca la zona de un wall (c=n: cuántas de las 3 confirmaciones tenía)
  x verde / roja    entrada larga / corta del bot (su apertura de la barra siguiente a la señal)
  x negra / dorada  salida: stop / objetivo (o cierre del día)
Líneas: walls INICIALES (9:20) call rojo / put verde con su zona, EXPECTED MOVEMENT (banda azul ±1 EM desde las 9:15), VWAP y sus bandas ±2σ (morado), Bollinger (gris); abajo RSI con 30/70; cartel de tipo de día (reversión/tendencia).
"""
from datetime import time
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.backends.backend_pdf import PdfPages  # noqa: E402

from .backtest import evaluate_signal, run_backtest, skip_reason  # noqa: E402
from .config import Params  # noqa: E402
from .days import build_days  # noqa: E402
from .indicators import add_indicators  # noqa: E402

FIRST_HOUR_END = time(10, 30)
GREEN, RED, BLUE, PURPLE, GOLD = "#2e7d32", "#c62828", "#1565c0", "#6a1b9a", "#f9a825"


def day_signals(b: pd.DataFrame, day: pd.Series, p: Params) -> pd.DataFrame:
    """Lo que el bot ve barra por barra durante la ventana de entradas (aunque ese día no opere)."""
    em = float(day["em_pts"])
    tol = p.zone_tol_frac * em
    call_w, put_w = day["call_wall"] + day["basis"], day["put_wall"] + day["basis"]
    rows = []
    for ts, row in b[(b.index.time >= p.entry_start) & (b.index.time <= p.reentry_end)].iterrows():
        sig = evaluate_signal(row, call_w, put_w, tol, p)
        if sig:
            ok = sig["conf"] >= p.confirmations_required and (sig["rejection_ok"] or not p.require_rejection)
            rows.append({"time": ts, **sig, "pasa": ok, "level": call_w if sig["side"] == "short" else put_w})
    return pd.DataFrame(rows)


def plot_day(date, b: pd.DataFrame, day: pd.Series, trades: pd.DataFrame, p: Params, why_not: str | None = None):
    b = b.between_time("09:00", "15:55")
    x = np.arange(len(b))
    pos = {ts: i for i, ts in enumerate(b.index)}
    em = float(day["em_pts"])
    tol = p.zone_tol_frac * em
    call_w, put_w = day["call_wall"] + day["basis"], day["put_wall"] + day["basis"]
    center_es = day["center_spx"] + day["basis"]

    fig, (ax, axr) = plt.subplots(2, 1, figsize=(15, 10), sharex=True, gridspec_kw={"height_ratios": [4, 1]})
    first_hour = [i for ts, i in pos.items() if time(9, 30) <= ts.time() < FIRST_HOUR_END]
    if first_hour:
        ax.axvspan(first_hour[0] - .5, first_hour[-1] + .5, color=GOLD, alpha=.12, label="primera hora (9:30-10:30)")
    up = b["close"] >= b["open"]
    ax.vlines(x, b["low"], b["high"], color=np.where(up, GREEN, RED), lw=1)
    ax.bar(x, (b["close"] - b["open"]).abs().clip(lower=.25), bottom=b[["open", "close"]].min(axis=1), width=.6,
           color=np.where(up, GREEN, RED), alpha=.85)
    ax.plot(x, b["vwap"], color=PURPLE, lw=1.4, label="VWAP")
    ax.plot(x, b["vwap_up"], color=PURPLE, lw=1, ls="--", alpha=.8, label="VWAP banda alta (+2σ)")
    ax.plot(x, b["vwap_dn"], color=PURPLE, lw=1, ls="--", alpha=.8, label="VWAP banda baja (-2σ)")
    ax.plot(x, b["bb_up"], color="gray", lw=.8, ls="-", alpha=.6, label="Bollinger 20/2")
    ax.plot(x, b["bb_dn"], color="gray", lw=.8, ls="-", alpha=.6)
    # EXPECTED MOVEMENT: banda sombreada centro ± EM (centro = precio de las 9:15 en coordenadas ES)
    ax.axhspan(center_es - em, center_es + em, color=BLUE, alpha=.05)
    for lvl, name in ((center_es - em, "-1 EM"), (center_es + em, "+1 EM")):
        ax.hlines(lvl, -1, len(b) - 1, color=BLUE, ls=":", lw=1.2)
        ax.text(len(b) - 2, lvl, f"{name} {lvl:.0f}", color=BLUE, va="bottom", ha="right", fontsize=8)
    ax.text(0.5, center_es, f"EXPECTED MOVEMENT ±{em:.1f} pts (centro {center_es:.0f})", color=BLUE, fontsize=10,
            weight="bold", va="bottom", transform=ax.get_yaxis_transform(), ha="center")
    # WALLS INICIALES (calculados con la cadena de las 9:20; no se mueven en el día)
    for lvl, col, name, spx in ((call_w, RED, "CALL WALL inicial", day["call_wall"]), (put_w, GREEN, "PUT WALL inicial", day["put_wall"])):
        if pd.notna(lvl):
            ax.hlines(lvl, -1, len(b) - 1, color=col, ls="-", lw=2.2)
            ax.fill_between([-1, len(b) - 1], lvl - tol, lvl + tol, color=col, alpha=.15)
            ax.text(len(b), lvl, f"{name}\n{lvl:.0f} ES (SPX {spx:.0f})", color=col, va="center", fontsize=9, weight="bold")

    # máximo y mínimo reales del día (sesión regular)
    rth = b.between_time("09:30", "15:55")
    for ts, val, name in ((rth["high"].idxmax(), rth["high"].max(), "Máx"), (rth["low"].idxmin(), rth["low"].min(), "Mín")):
        inwin = ts.time() < FIRST_HOUR_END
        ax.plot(pos[ts], val, marker="x", ms=15, mew=3, color=BLUE, ls="none")
        ax.annotate(f"{name} {val:.2f} ({ts:%H:%M}){' - 1a hora' if inwin else ''}", (pos[ts], val), textcoords="offset points",
                    xytext=(8, 10 if name == "Máx" else -16), color=BLUE, fontsize=9, weight="bold")

    sigs = day_signals(b, day, p)
    for _, s in sigs.iterrows():
        if s["time"] in pos:
            ax.plot(pos[s["time"]], s["level"], marker="x", ms=7, mew=1.5, color="gray", ls="none")
            ax.annotate(f"c={s['conf']}{'' if s['pasa'] else '*'}", (pos[s["time"]], s["level"]), textcoords="offset points",
                        xytext=(4, -12 if s["side"] == "short" else 6), fontsize=7, color="gray")

    for _, t in trades.iterrows():
        col = GREEN if t["side"] == "long" else RED
        ax.plot(pos[t["entry_time"]], t["entry"], marker="x", ms=16, mew=3.5, color=col, ls="none")
        ax.annotate(f"E{t['n']} {'largo' if t['side'] == 'long' else 'corto'} {t['entry']:.2f}", (pos[t["entry_time"]], t["entry"]),
                    textcoords="offset points", xytext=(8, 8), color=col, fontsize=9, weight="bold")
        xt = pos.get(t["exit_time"], len(b) - 1)
        ax.plot(xt, t["exit"], marker="x", ms=13, mew=3, color="black" if t["reason"] == "stop" else GOLD, ls="none")
        ax.annotate(f"{t['reason']} {t['usd']:+.0f} USD", (xt, t["exit"]), textcoords="offset points", xytext=(8, -14), fontsize=9)

    ax.set_xlim(-1, len(b) + 12)                # espacio a la derecha para las etiquetas de los niveles
    ticks = [i for ts, i in pos.items() if ts.minute == 0]
    axr.set_xticks(ticks)
    axr.set_xticklabels([b.index[i].strftime("%H:%M") for i in ticks])
    axr.plot(x, b["rsi"], color=BLUE, lw=1.2)
    for lvl in (p.rsi_low, p.rsi_high):
        axr.axhline(lvl, color="gray", ls="--", lw=1)
    axr.axhline(50, color="gray", ls=":", lw=.6)
    axr.fill_between(x, p.rsi_high, 100, color=RED, alpha=.08)
    axr.fill_between(x, 0, p.rsi_low, color=GREEN, alpha=.08)
    if first_hour:
        axr.axvspan(first_hour[0] - .5, first_hour[-1] + .5, color=GOLD, alpha=.12)
    axr.set_ylim(0, 100)
    axr.set_ylabel(f"RSI {p.rsi_period}")
    axr.grid(alpha=.25)
    pos_gamma = day["gex_bn"] > 0
    banner = "DÍA DE REVERSIÓN (gamma positivo)" if pos_gamma else "DÍA DE TENDENCIA (gamma negativo)"
    ax.text(0.99, 0.985, banner, transform=ax.transAxes, ha="right", va="top", fontsize=13, weight="bold", color="white",
            bbox=dict(boxstyle="round,pad=0.4", fc=GREEN if pos_gamma else RED, ec="none"))
    regime = "gamma POSITIVO (reversión)" if pos_gamma else "gamma NEGATIVO (tendencia)"
    decision = f"OPERA ({len(trades)} operación(es))" if len(trades) else (f"NO OPERA: {why_not}" if why_not else "opera pero no hubo entrada")
    ax.set_title(f"{pd.Timestamp(date):%a %d-%b-%Y} | {regime} | GEX {day['gex_bn']:+.1f} mil millones | EXPECTED MOVEMENT {em:.1f} pts | {decision}", fontsize=12, weight="bold")
    ax.text(0.01, 0.01, f"base ES-SPX {day['basis']:.1f} | salto nocturno {day['gap_nocturno']:+.1f} pts | c=n: confirmaciones (de 3) | * = no pasa el filtro",
            transform=ax.transAxes, fontsize=8, color="dimgray")
    ax.set_ylabel("ES")
    ax.legend(loc="upper left", fontsize=8)
    ax.grid(alpha=.25)
    fig.tight_layout()
    return fig


def zone_stats(date, b, day, trades, p, why_not) -> dict:
    rth = b.between_time("09:30", "15:55")
    em = float(day["em_pts"])
    call_w, put_w = day["call_wall"] + day["basis"], day["put_wall"] + day["basis"]
    th, tl = rth["high"].idxmax(), rth["low"].idxmin()
    lim = FIRST_HOUR_END
    sigs = day_signals(b, day, p)
    return {
        "date": pd.Timestamp(date).date(), "regimen": "reversion" if day["gex_bn"] > 0 else "tendencia", "opera": bool(len(trades)),
        "motivo_no_opera": why_not or "", "em_pts": em, "maximo": rth["high"].max(), "minimo": rth["low"].min(),
        "hora_maximo": th.strftime("%H:%M"), "hora_minimo": tl.strftime("%H:%M"),
        "maximo_en_1a_hora": th.time() < lim, "minimo_en_1a_hora": tl.time() < lim,
        "call_wall_es": call_w, "put_wall_es": put_w,
        "maximo_menos_call_wall_EM": (rth["high"].max() - call_w) / em if pd.notna(call_w) else np.nan,
        "minimo_menos_put_wall_EM": (rth["low"].min() - put_w) / em if pd.notna(put_w) else np.nan,
        "toques_de_zona": len(sigs), "senales_que_pasan": int(sigs["pasa"].sum()) if len(sigs) else 0,
        "operaciones": len(trades), "resultado_usd": float(trades["usd"].sum()) if len(trades) else 0.0,
    }


def make_study(summary: pd.DataFrame, bars: pd.DataFrame, out_dir, p: Params = Params(), wall_mode: str = "oi_1em") -> pd.DataFrame:
    out = Path(out_dir)
    (out / "png").mkdir(parents=True, exist_ok=True)
    days, _ = build_days(summary, bars, wall_mode=wall_mode)
    if days.empty:
        return pd.DataFrame()
    trades, _ = run_backtest(bars, days, p)
    ind = add_indicators(bars, p)
    by_day = {d: g for d, g in ind.groupby(ind.index.date)}
    rows = []
    with PdfPages(out / "estudio_dias.pdf") as pdf:
        for key, day in days.iterrows():
            date = pd.Timestamp(key).date()
            b = by_day.get(date)
            if b is None or len(b.between_time("09:30", "15:55")) < p.min_session_bars:
                continue
            t = trades[trades["date"] == date] if len(trades) else trades
            why = skip_reason(day, p)
            fig = plot_day(date, b, day, t, p, why)
            fig.savefig(out / "png" / f"{date}.png", dpi=110)
            pdf.savefig(fig)
            plt.close(fig)
            rows.append(zone_stats(date, b, day, t, p, why))
    table = pd.DataFrame(rows)
    table.to_csv(out / "estudio_zonas.csv", index=False)
    return table


def summarize_zones(t: pd.DataFrame) -> list[str]:
    """¿El máximo/mínimo del día cae cerca del wall? (muestra chica: leer con cuidado)"""
    if t.empty:
        return ["Sin días para estudiar."]
    lines = [f"Días estudiados: {len(t)}"]
    for col, name, side in (("maximo_menos_call_wall_EM", "máximo del día", "call wall"), ("minimo_menos_put_wall_EM", "mínimo del día", "put wall")):
        d = t[col].dropna()
        if len(d):
            lines.append(f"El {name} quedó a ±0.25 EM del {side} en {int((d.abs() <= .25).sum())} de {len(d)} días, "
                         f"a ±0.5 EM en {int((d.abs() <= .5).sum())}; distancia mediana {d.abs().median():.2f} EM.")
    h = t[t["maximo_en_1a_hora"]]["maximo_menos_call_wall_EM"].dropna()
    l = t[t["minimo_en_1a_hora"]]["minimo_menos_put_wall_EM"].dropna()
    lines.append(f"Máximo en la 1a hora: {int(t['maximo_en_1a_hora'].sum())} días; de ellos, a ±0.5 EM del call wall: {int((h.abs() <= .5).sum())}.")
    lines.append(f"Mínimo en la 1a hora: {int(t['minimo_en_1a_hora'].sum())} días; de ellos, a ±0.5 EM del put wall: {int((l.abs() <= .5).sum())}.")
    return lines
