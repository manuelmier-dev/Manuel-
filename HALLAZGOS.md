# Registro de hipótesis probadas (bot SPX 0DTE / ES)

Método fijo: reglas definidas ANTES de ver el resultado, años de datos, comparación contra azar (niveles o señales falsos), entrenamiento vs
comprobación, costos de 29 USD por operación (comisión 4 + deslizamiento 0.25 pts por lado), y criterio de aprobación p < 0.008 con t > 2.
Muestra pequeña = no concluye. Una regla "ganadora" entre muchas se vuelve a probar en una muestra que no se usó para elegirla.

| Fecha | Hipótesis | Datos | Resultado | Veredicto |
|---|---|---|---|---|
| 14-15 oct 2026 | Fade en walls de OI con confirmaciones (VWAP, Bollinger, RSI), reglas de Manuel | Theta + ES, 956 días (2022-26) | 395 operaciones, 17.5% aciertos, -14.7 mil USD, factor 0.86 | Sin ventaja |
| 15 oct 2026 | Gamma negativo = día de tendencia (rango y cierre) | 961 días | Rango/EM 2.05 vs 2.07; cierra en extremo 46% vs 50% | No se sostiene |
| 15 oct 2026 | Los walls de OI marcan el máx/mín de la 1a hora | 960 días, contra niveles falsos | Distancia 0.36 EM vs 0.35 al azar, p = 0.89 y 0.49 | No marcan nada |
| 15 oct 2026 | Placebo: la estrategia con walls falsos | 956 días, 40 repeticiones | Reales -15.5 mil vs falsos -22.9 mil (p 0.20); 1a entrada p 0.48 | Los walls no aportan |
| 15 oct 2026 | Mapa de sensibilidad con división (48 combinaciones) | entrenamiento 2022-sep 2025, comprobación oct 2025+ | 0 de 48 ganan en la comprobación; correlación 0.10 | Era suerte |
| 15 oct 2026 | Ruptura del primer rango en gamma negativo (12 variantes) | 406 días | Factor 0.88 a 1.07, las "mejores" son selección | Sin ventaja demostrada |
| 15 oct 2026 | M1/M2/M3 momento hacia el cierre (1 operación al día) | 950 días | -0.32 / +0.13 / -0.12 pts brutos, todos p > 0.39 | No existe |
| 15 oct 2026 | N1 noche (comprar cierre, vender apertura) | 764 días | +0.33 pts netos, t = 0.28 | Cero tras costos |
| 15 oct 2026 | G2 contra el hueco nocturno (9:30 a 11:00) | 2022-26: +1.6 pts, p = 0.044 (la mejor de 6, no pasó el criterio) | Muestra nueva 2010-22 + total (3,277 operaciones): +0.08 pts brutos, -0.50 netos, p = 0.37; 3 de 17 años positivos | NO se replica: era suerte |

## Conclusiones
- En 4.4 años de 0DTE y 16.8 años de ES, ninguna regla intradía probada tiene ventaja después de costos.
- Los niveles de OI/gamma (walls) no aportan información sobre dónde se hace el máximo/mínimo ni mejoran el resultado.
- La gamma estimada con precios de opciones no separa días de reversión de días de tendencia. (No se probó con flujo con signo, que es lo que
  realmente describe la posición de los market makers.)
- Hallazgo estructural verdadero pero sin ventaja operable: el máximo o el mínimo del día cae en la primera hora el 71% de los días
  (34% el máximo, 39% el mínimo); una caminata al azar con volatilidad alta al abrir da ~66%.

## Mecánica construida (sirve para cualquier estrategia futura)
Descarga de Theta (historia 0DTE) y de ES por la API de TradeStation; backtest con las mismas reglas que el robot; robot que decide qué haría
(bot/live.py) y envía órdenes al SIMULADOR con stop y objetivo ligados (bot/ts_orders.py, probado: compra, OCO, cancela, cierra).
