from dataclasses import dataclass
from datetime import time


@dataclass(frozen=True)
class Params:
    # Filtros del día (se evalúan con datos disponibles ANTES de las 9:30 NY)
    gex_min_bn: float = 0.5            # GEX total debe ser > 0.5 mil millones; negativo o dentro de ±0.5 = no operar
    min_expected_move_pts: float = 20.0

    # Salidas, como fracción del movimiento esperado (EM)
    stop_frac: float = 0.20
    target_frac: float = 0.90

    # Horarios (hora de Nueva York)
    entry_start: time = time(9, 30)
    entry_end: time = time(10, 30)     # límite para la 1a entrada
    reentry_end: time = time(11, 30)   # límite para la 2a entrada (SUPUESTO, ajustable)
    flat_time: time = time(15, 55)     # cierre forzado (SUPUESTO, ajustable)
    max_entries: int = 2               # la 2a solo después de un stop

    # Zona alrededor del wall, como fracción del EM
    zone_tol_frac: float = 0.10

    # Confirmaciones (VWAP, Bollinger, RSI)
    confirmations_required: int = 2
    bb_period: int = 20
    bb_std: float = 2.0
    vwap_band_std: float = 2.0
    rsi_period: int = 14
    rsi_high: float = 70.0
    rsi_low: float = 30.0

    # Costos (ES)
    point_value: float = 50.0
    slippage_pts: float = 0.25         # por lado, en contra
    commission_rt: float = 4.0         # USD por contrato, ida y vuelta (SUPUESTO)
