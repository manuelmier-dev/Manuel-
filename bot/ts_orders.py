"""Órdenes en el SIMULADOR de TradeStation (cuenta de práctica, 1 contrato de ES). NUNCA habla con la cuenta real.

*** NO PROBADO contra la API real: Claude no tiene acceso a TradeStation. Los nombres de campos salen de la documentación pública
*** (API v3, consultada de memoria el 15-oct-2026); cada comando nuevo se prueba primero SIN enviar nada.

Seguridad (se comprueba en el código y en las pruebas):
  - La dirección es SIEMPRE la del simulador (SIM_BASE). No hay forma de apuntar a la cuenta real desde aquí.
  - Solo se acepta una cuenta cuyo AccountID empiece con "SIM".
  - Enviar o cancelar órdenes exige --enviar; sin esa palabra solo se muestra qué se haría.
  - Cantidad máxima: 1 contrato.
Uso (en el servidor; el token se lee del archivo, no se imprime):
  python -m bot.ts_orders cuentas   <ts_tokens.json>
  python -m bot.ts_orders confirmar <ts_tokens.json> <cuenta SIM>   # pide a la API VALIDAR una compra lejana de 1 ES; no envía la orden
  python -m bot.ts_orders prueba    <ts_tokens.json> <cuenta SIM> [--enviar]   # envía esa compra lejana al simulador y la cancela
  python -m bot.ts_orders ciclo     <ts_tokens.json> <cuenta SIM> [--enviar]   # compra a mercado, OCO lejano, cancela y cierra (mercado abierto)
"""
import json
import sys
import urllib.error
import urllib.request
from datetime import date, timedelta

SIM_BASE = "https://sim-api.tradestation.com/v3"
MAX_QTY = 1
MONTH_CODE = {3: "H", 6: "M", 9: "U", 12: "Z"}


class SafetyError(RuntimeError):
    pass


def assert_sim_account(account_id: str) -> str:
    if not str(account_id).upper().startswith("SIM"):
        raise SafetyError(f"La cuenta {account_id!r} no es del simulador (debe empezar con SIM). No se envía nada.")
    return str(account_id)


def third_friday(year: int, month: int) -> date:
    d = date(year, month, 1)
    first_friday = d + timedelta(days=(4 - d.weekday()) % 7)
    return first_friday + timedelta(days=14)


def es_front_symbol(today: date, roll_days: int = 8) -> str:
    """Contrato trimestral de ES vigente (ej. ESZ26). Se cambia al siguiente `roll_days` días antes del vencimiento (3er viernes)."""
    y = today.year
    for m in (3, 6, 9, 12):
        if third_friday(y, m) - timedelta(days=roll_days) > today:
            return f"ES{MONTH_CODE[m]}{str(y)[-2:]}"
    return f"ESH{str(y + 1)[-2:]}"


def order_body(account_id: str, symbol: str, side: str, order_type: str, qty: int = 1, limit=None, stop=None) -> dict:
    """Cuerpo de una orden. side: BUY o SELL (en futuros no hay BUYTOCOVER/SELLSHORT). order_type: Market | Limit | StopMarket."""
    assert_sim_account(account_id)
    if qty != MAX_QTY:
        raise SafetyError(f"Solo se permite {MAX_QTY} contrato (se pidió {qty}).")
    if side not in ("BUY", "SELL"):
        raise ValueError("side debe ser BUY o SELL")
    body = {"AccountID": account_id, "Symbol": symbol, "Quantity": str(qty), "OrderType": order_type, "TradeAction": side,
            "TimeInForce": {"Duration": "DAY"}, "Route": "Intelligent"}
    if order_type == "Limit":
        body["LimitPrice"] = f"{limit:.2f}"
    if order_type == "StopMarket":
        body["StopPrice"] = f"{stop:.2f}"
    return body


def far_limit_price(last: float, pts: float = 300.0, tick: float = 0.25) -> float:
    """Precio de compra muy por debajo del mercado: una orden de prueba que NO se ejecutaría aunque se enviara."""
    return round((last - pts) / tick) * tick


def call(method: str, path: str, token: str, body: dict | None = None, timeout: int = 60) -> tuple[int, dict]:
    url = SIM_BASE + path                                            # siempre el simulador
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            txt = r.read().decode("utf-8")
            return r.status, (json.loads(txt) if txt.strip() else {})
    except urllib.error.HTTPError as e:
        txt = e.read().decode("utf-8", "replace")
        try:
            return e.code, json.loads(txt)
        except ValueError:
            return e.code, {"raw": txt[:300]}


def list_accounts(token: str, fetch=call) -> list[dict]:
    status, payload = fetch("GET", "/brokerage/accounts", token)
    if status != 200:
        raise RuntimeError(f"La API del simulador respondió {status}: {str(payload)[:300]}")
    return payload.get("Accounts", [])


def place_order(token: str, body: dict, fetch=call) -> str:
    """Envía UNA orden al simulador y devuelve su OrderID. (El cuerpo ya pasó por order_body: SIM, 1 contrato.)"""
    assert_sim_account(body["AccountID"])
    status, payload = fetch("POST", "/orderexecution/orders", token, body)
    orders = payload.get("Orders") or []
    if status != 200 or not orders or not orders[0].get("OrderID"):
        raise RuntimeError(f"El simulador no aceptó la orden (HTTP {status}): {str(payload)[:400]}")
    return str(orders[0]["OrderID"])


def cancel_order(token: str, order_id: str, fetch=call) -> dict:
    status, payload = fetch("DELETE", f"/orderexecution/orders/{order_id}", token)
    if status != 200:
        raise RuntimeError(f"No se pudo cancelar {order_id} (HTTP {status}): {str(payload)[:300]}")
    return payload


def order_status(token: str, account: str, order_id: str, fetch=call) -> dict:
    assert_sim_account(account)
    status, payload = fetch("GET", f"/brokerage/accounts/{account}/orders", token)
    if status != 200:
        raise RuntimeError(f"No pude leer las órdenes (HTTP {status}): {str(payload)[:300]}")
    return next((o for o in payload.get("Orders", []) if str(o.get("OrderID")) == str(order_id)), {})


FILLED = {"FLL"}
DEAD = {"REJ", "OUT", "CAN", "EXP", "UCN", "TSC"}


def get_positions(token: str, account: str, fetch=call) -> list[dict]:
    assert_sim_account(account)
    status, payload = fetch("GET", f"/brokerage/accounts/{account}/positions", token)
    if status != 200:
        raise RuntimeError(f"No pude leer las posiciones (HTTP {status}): {str(payload)[:300]}")
    return payload.get("Positions", [])


def net_qty(positions: list[dict], symbol: str) -> int:
    """Contratos netos del símbolo: + largo, - corto."""
    total = 0
    for p in positions:
        if p.get("Symbol") == symbol:
            q = int(float(p.get("Quantity", 0)))
            total += q if str(p.get("LongShort", "Long")).lower().startswith("l") else -q
    return total


def fill_price(order: dict):
    if order.get("FilledPrice") not in (None, "", "0"):
        return float(order["FilledPrice"])
    legs = order.get("Legs") or []
    return float(legs[0]["ExecutionPrice"]) if legs and legs[0].get("ExecutionPrice") else None


def wait_fill(token: str, account: str, order_id: str, fetch=call, sleep=lambda s: None, tries: int = 15) -> float:
    """Espera a que la orden se llene y devuelve el precio de llenado. Si muere o no se llena a tiempo, avisa."""
    for _ in range(tries):
        o = order_status(token, account, order_id, fetch)
        if o.get("Status") in FILLED:
            px = fill_price(o)
            if px is None:
                raise RuntimeError(f"La orden {order_id} se llenó pero no encuentro el precio: {str(o)[:300]}")
            return px
        if o.get("Status") in DEAD:
            raise RuntimeError(f"La orden {order_id} no se llenó: {o.get('Status')} {o.get('StatusDescription')}")
        sleep(1)
    raise RuntimeError(f"La orden {order_id} sigue sin llenarse después de {tries} intentos")


def place_oco(token: str, account: str, symbol: str, exit_side: str, stop_price: float, target_price: float, fetch=call) -> tuple[str, str]:
    """Dos órdenes de salida ligadas (si una se ejecuta, se cancela la otra): STOP y LIMIT de 1 contrato. Devuelve (id_stop, id_objetivo)."""
    stop = order_body(account, symbol, exit_side, "StopMarket", stop=stop_price)
    tgt = order_body(account, symbol, exit_side, "Limit", limit=target_price)
    status, payload = fetch("POST", "/orderexecution/ordergroups", token, {"Type": "OCO", "Orders": [stop, tgt]})
    orders = payload.get("Orders") or []
    if status != 200 or len(orders) != 2 or not all(o.get("OrderID") for o in orders):
        raise RuntimeError(f"El simulador no aceptó el grupo OCO (HTTP {status}): {str(payload)[:400]}")
    return str(orders[0]["OrderID"]), str(orders[1]["OrderID"])


def flatten(token: str, account: str, symbol: str, fetch=call, sleep=lambda s: None) -> int:
    """Cierra a mercado lo que haya abierto en ese símbolo. Devuelve los contratos que había."""
    q = net_qty(get_positions(token, account, fetch), symbol)
    if q == 0:
        return 0
    if abs(q) > MAX_QTY:
        raise SafetyError(f"Hay {q} contratos abiertos (el máximo es {MAX_QTY}); no opero más y aviso.")
    oid = place_order(token, order_body(account, symbol, "SELL" if q > 0 else "BUY", "Market"), fetch)
    wait_fill(token, account, oid, fetch, sleep)
    return q


def probar_ciclo_mercado(token: str, account: str, today: date, send: bool, fetch=call, sleep=lambda s: None, dist: float = 200.0) -> list[str]:
    """Etapa 5a, SOLO simulador: compra 1 ES a mercado, pone STOP y objetivo OCO muy lejos (+-200 pts), los cancela y cierra a mercado.
    Prueba la mecánica completa con llenados reales del simulador. Si algo falla, limpia (cancela y cierra) antes de avisar."""
    account = assert_sim_account(account)
    symbol = es_front_symbol(today)
    log = [f"Ciclo completo en el simulador: comprar 1 {symbol} a mercado, OCO a +-{dist:.0f} pts, cancelar, cerrar."]
    if not send:
        return log + ["NO se envía nada (falta --enviar)."]
    if net_qty(get_positions(token, account, fetch), symbol) != 0:
        raise SafetyError("Ya hay una posición abierta en esa cuenta; no empiezo la prueba.")
    ids: list[str] = []
    try:
        oid = place_order(token, order_body(account, symbol, "BUY", "Market"), fetch)
        px = wait_fill(token, account, oid, fetch, sleep)
        log.append(f"Compra llenada a {px}")
        log.append(f"Posición neta: {net_qty(get_positions(token, account, fetch), symbol)}")
        sid, tid = place_oco(token, account, symbol, "SELL", px - dist, px + dist, fetch)
        ids = [sid, tid]
        log.append(f"OCO enviado: stop {px - dist:.2f} (id {sid}) / objetivo {px + dist:.2f} (id {tid})")
        sleep(2)
        log.append("Estados: " + ", ".join(f"{i}={order_status(token, account, i, fetch).get('Status')}" for i in ids))
    finally:
        for i in ids:
            try:
                cancel_order(token, i, fetch)
            except RuntimeError as e:
                log.append(f"(al cancelar {i}: {e})")
        sleep(2)
        closed = flatten(token, account, symbol, fetch, sleep)
        log.append(f"Cierre a mercado de {closed} contrato(s); posición final: {net_qty(get_positions(token, account, fetch), symbol)}")
    return log


def probar_ciclo(token: str, account: str, last: float, today: date, send: bool, fetch=call, sleep=lambda s: None) -> list[str]:
    """Etapa 3: enviar una compra muy lejana (no se ejecuta), verla viva, cancelarla y comprobar que quedó cancelada. Solo con send=True."""
    body = order_body(assert_sim_account(account), es_front_symbol(today), "BUY", "Limit", limit=far_limit_price(last))
    log = [f"Orden de prueba: {body['TradeAction']} 1 {body['Symbol']} límite {body['LimitPrice']} (ES está en {last})"]
    if not send:
        return log + ["NO se envía nada (falta --enviar)."]
    oid = place_order(token, body, fetch)
    log.append(f"Enviada. OrderID {oid}")
    sleep(2)
    st = order_status(token, account, oid, fetch)
    log.append(f"Estado tras enviarla: {st.get('Status')} - {st.get('StatusDescription')}")
    log.append(f"Cancelación: {cancel_order(token, oid, fetch)}")
    sleep(2)
    st = order_status(token, account, oid, fetch)
    log.append(f"Estado final: {st.get('Status')} - {st.get('StatusDescription')}")
    return log


if __name__ == "__main__":
    from .ts_bars import read_token
    cmd = sys.argv[1]
    token = read_token(sys.argv[2])
    if cmd == "cuentas":
        try:
            accts = list_accounts(token)
        except RuntimeError as e:
            print(e)
            sys.exit(1)
        print(f"Cuentas visibles en el simulador: {len(accts)}   |   contrato ES vigente hoy: {es_front_symbol(date.today())}")
        for a in accts:
            print({k: a.get(k) for k in ("AccountID", "AccountType", "Status", "Currency")})
    elif cmd == "confirmar":
        from datetime import datetime, timezone

        import pandas as pd

        from .ts_bars import build_url, fetch_json
        account = assert_sim_account(sys.argv[3])
        st, payload = fetch_json(build_url("@ES", pd.Timestamp(datetime.now(timezone.utc)), barsback=1), token)
        bars = payload.get("Bars") or []
        if st != 200 or not bars:
            print(f"No pude leer el precio actual de ES (HTTP {st}).")
            sys.exit(1)
        last = float(bars[-1]["Close"])
        symbol = es_front_symbol(date.today())
        body = order_body(account, symbol, "BUY", "Limit", limit=far_limit_price(last))
        print(f"Precio de ES ahora: {last}.  Pido VALIDAR (no enviar): {body}")
        status, answer = call("POST", "/orderexecution/orderconfirm", token, body)
        print(f"HTTP {status}: {json.dumps(answer)[:600]}")
    elif cmd == "prueba":
        import time
        from datetime import datetime, timezone

        import pandas as pd

        from .ts_bars import build_url, fetch_json
        account = assert_sim_account(sys.argv[3])
        st, payload = fetch_json(build_url("@ES", pd.Timestamp(datetime.now(timezone.utc)), barsback=1), token)
        bars = payload.get("Bars") or []
        if st != 200 or not bars:
            print(f"No pude leer el precio actual de ES (HTTP {st}).")
            sys.exit(1)
        print("\n".join(probar_ciclo(token, account, float(bars[-1]["Close"]), date.today(), "--enviar" in sys.argv, sleep=time.sleep)))
    elif cmd == "ciclo":
        import time
        account = assert_sim_account(sys.argv[3])
        print("\n".join(probar_ciclo_mercado(token, account, date.today(), "--enviar" in sys.argv, sleep=time.sleep)))
