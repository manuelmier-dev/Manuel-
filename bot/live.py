"""Robot de órdenes, ETAPA 4: decide QUÉ HARÍA ahora mismo con las MISMAS reglas del backtest. NO envía ninguna orden.

Idea: en cada cierre de barra se repite el backtest del día con las barras ya cerradas (más una barra "sintética" que abre al último precio,
que es donde entraría una orden de mercado). Así lo que se mide en el backtest y lo que haría el robot son lo mismo.

Uso (en el servidor con Theta Terminal y el token de TradeStation):
  python -m bot.live <ts_tokens.json> [--fecha AAAA-MM-DD] [--hora HH:MM]
Sin --fecha usa hoy y la hora actual de Nueva York. Con una fecha pasada repite ese día (hora por defecto 16:00): sirve para comprobar que el robot
reproduce el backtest.
*** NO PROBADO contra datos en vivo.
"""
import sys
from dataclasses import replace
from datetime import date, time

import pandas as pd

from .backtest import run_backtest, skip_reason
from .config import Params
from .days import build_days

NY = "America/New_York"
BAR = pd.Timedelta(minutes=5)


def bars_from_api(api_utc_close_stamp: pd.DataFrame) -> pd.DataFrame:
    """La API da la hora de CIERRE de cada barra en UTC; el resto del código usa la hora de INICIO en Nueva York."""
    out = api_utc_close_stamp.copy()
    out.index = (out.index - BAR).tz_convert(NY)
    return out.sort_index()


def simulate(summary_row: pd.DataFrame, bars: pd.DataFrame, now: pd.Timestamp, p: Params = Params()) -> dict:
    """Qué dice el backtest del día con las barras cerradas a `now`. Devuelve {estado, motivo, dia, operaciones}."""
    closed = bars[bars.index + BAR <= now]
    if closed.empty or closed.index[-1].date() != now.date():
        return {"estado": "SIN_DATOS", "motivo": "todavía no hay barras cerradas de hoy"}
    last = closed.iloc[-1]
    synth_ts = closed.index[-1] + BAR
    synth = pd.DataFrame({"open": [last["close"]], "high": [last["close"]], "low": [last["close"]], "close": [last["close"]], "volume": [0.0]},
                         index=pd.DatetimeIndex([synth_ts]))
    sim = pd.concat([closed, synth])
    days, skipped = build_days(summary_row, sim)
    if days.empty:
        return {"estado": "NO_OPERA", "motivo": "; ".join(skipped) or "sin datos del día"}
    day = days.iloc[0]
    why = skip_reason(day, p)
    info = {"gex_bn": float(day["gex_bn"]), "em_pts": float(day["em_pts"]), "call_wall_es": float(day["call_wall"] + day["basis"]),
            "put_wall_es": float(day["put_wall"] + day["basis"]), "base_es_spx": float(day["basis"])}
    if why:
        return {"estado": "NO_OPERA", "motivo": why, "dia": info}
    trades, _ = run_backtest(sim, days, replace(p, min_session_bars=0))
    ops = []
    for _, t in trades.iterrows():
        if t["entry_time"] == synth_ts:
            st = "ENTRAR_AHORA"
        elif t["reason"] == "cierre_dia" and t["exit_time"] == synth_ts and now.time() < p.flat_time:
            st = "ABIERTA"                               # todavía no toca ni el stop ni el objetivo
        else:
            st = "CERRADA"
        ops.append({"n": int(t["n"]), "lado": t["side"], "estado": st, "hora_entrada": t["entry_time"], "entrada": float(t["entry"]),
                    "stop": float(t["stop"]), "objetivo": float(t["target"]), "motivo_salida": t["reason"] if st == "CERRADA" else ""})
    return {"estado": "OPERA", "dia": info, "operaciones": ops}


def describe(res: dict, now: pd.Timestamp) -> list[str]:
    lines = [f"Hora de Nueva York: {now:%Y-%m-%d %H:%M}"]
    d = res.get("dia")
    if d:
        lines.append(f"Gamma {d['gex_bn']:+.1f} mil millones | movimiento esperado {d['em_pts']:.1f} pts | call wall {d['call_wall_es']:.2f} | "
                     f"put wall {d['put_wall_es']:.2f} (en ES; base ES-SPX {d['base_es_spx']:.1f})")
    if res["estado"] != "OPERA":
        return lines + [f"{res['estado']}: {res.get('motivo', '')}"]
    if not res["operaciones"]:
        return lines + ["OPERA hoy, pero todavía no hay señal."]
    for o in res["operaciones"]:
        lines.append(f"Operación {o['n']}: {o['lado'].upper()} | {o['estado']} | entrada {o['entrada']:.2f} | stop {o['stop']:.2f} | objetivo {o['objetivo']:.2f}"
                     + (f" | salió por {o['motivo_salida']}" if o["motivo_salida"] else ""))
    now_acts = [o for o in res["operaciones"] if o["estado"] == "ENTRAR_AHORA"]
    for o in now_acts:
        side = "BUY" if o["lado"] == "long" else "SELL"
        exit_side = "SELL" if o["lado"] == "long" else "BUY"
        lines.append(f"==> ENVIARÍA (si estuviera activo): {side} 1 ES a mercado; luego OCO: {exit_side} STOP {o['stop']:.2f} / {exit_side} LIMIT {o['objetivo']:.2f}")
    return lines


def get_inputs(trade_date: date, token: str):
    """Datos del día: Theta (cotizaciones de las 9:20 y Open Interest) y barras de ES de TradeStation."""
    from .theta_client import at_time_quote, normalize_oi, normalize_quotes, open_interest
    from .theta_snapshot import summary_from_theta
    from .ts_bars import download_bars
    d = pd.Timestamp(trade_date)
    q = normalize_quotes(at_time_quote("SPXW", d, d))
    oi = normalize_oi(open_interest("SPXW", d, d))
    row = summary_from_theta(d, q, oi)
    summary = pd.DataFrame([row])
    api = download_bars("@ES", d - pd.Timedelta(days=5), d, token)
    return summary, bars_from_api(api)


if __name__ == "__main__":
    from .ts_bars import read_token
    token = read_token(sys.argv[1])
    args = sys.argv[2:]
    day = date.fromisoformat(args[args.index("--fecha") + 1]) if "--fecha" in args else pd.Timestamp.now(tz=NY).date()
    if "--hora" in args:
        hh, mm = map(int, args[args.index("--hora") + 1].split(":"))
        now = pd.Timestamp.combine(day, time(hh, mm)).tz_localize(NY)
    elif "--fecha" in args:
        now = pd.Timestamp.combine(day, time(16, 0)).tz_localize(NY)
    else:
        now = pd.Timestamp.now(tz=NY)
    summary, bars = get_inputs(day, token)
    print("\n".join(describe(simulate(summary, bars, now), now)))
