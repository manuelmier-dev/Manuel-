# Reglas congeladas (versión 1.2, 14-oct-2026)

Se congelan hoy. Todo lo que ocurra **después del 14-oct-2026** es "fuera de muestra" y NO se usa para ajustar estas reglas
hasta tener un periodo largo (mínimo 60 días operables). Si hay que cambiar algo, se anota aquí con fecha y motivo.

## Día operable
- GEX total (cadena 0DTE, ±90 pts) **positivo**. Gamma negativo = día de tendencia: no se opera (estrategia de tendencia pendiente).
- Movimiento esperado de TradeStation **≥ 20 puntos**.
- Archivo de cadena exportado **antes de las 9:30 NY** y con un solo vencimiento (0DTE).

## Entrada
- Wall = mayor Open Interest dentro de ±1 EM del **precio real de las 9:20** (calls arriba, puts abajo). Precio real = ES(9:15) − base,
  base = cierre de ES del día anterior − spot del archivo (mediana de 5 días).
- Zona = wall ± 10% del EM. Señal al cierre de una barra de 5 min, **durante toda la primera hora (9:30 a 10:30)**.
- Confirmación: al menos 2 de 3 (VWAP ±2σ, Bollinger 20/2, RSI 14 en 70/30).
- Entrada en la apertura de la barra siguiente. Una segunda entrada solo tras un stop, hasta las 11:30, con confirmaciones nuevas.

## Salida
- Stop = 20% del EM. Objetivo = 90% del EM o el wall contrario (lo que llegue primero). Cierre forzado 15:55.

## Cambios hechos
- 14-oct (v1.2): **se revierte** la regla de saltar la primera barra. Era mía, no de Manuel: su idea es identificar en la primera hora las zonas del máximo y mínimo del día. Queda solo como prueba en el mapa de sensibilidad (`entry_start` 9:35).
- 14-oct (v1.1, revertido arriba): la primera barra dejaba de generar señal (0 de 4 entradas de esa barra ganaron). Stop se queda en 20%: más amplio fue peor
  en 29 de 36 comparaciones. Wall se queda en ±1 EM: 15 de 36 combinaciones con ganancia, contra 10 (global) y 5 (gamma).
- En prueba, NO adoptado: `require_rejection` (la barra de la señal debe cerrar del lado de adentro del wall).
