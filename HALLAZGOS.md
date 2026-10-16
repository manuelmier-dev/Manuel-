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

| 15 oct 2026 | Estrategia de Manuel: compra de reversión con MACD (histograma), RSI < 33 y precio bajo la banda baja -2σ del VWAP Globex, entrada 7:30-10:30 NY, 1 por día, salida por regla o 15:55 | ES 24 h, 16.8 años | Modo B: 106 operaciones (~6 al año), +4.5 pts netos, t = 1.87, 60% aciertos, +24 mil USD, peor caída -8.1 mil, placebo p = 0.002, 8 de 11 años positivos. Modo A: +2.2 pts, t = 0.80 | Candidata débil: no pasa t > 2; rara y de poco valor en dólares |
| 15 oct 2026 | Sensibilidad de la anterior (24 combinaciones: RSI 30/33/38/42, banda 1σ/2σ, MACD A/B/ninguno) | ES 16.8 años | Con banda 2σ las 12 combinaciones son positivas (+2.2 a +5.0 pts; sin MACD t = 1.9 a 2.2; n = 168 a 198). Con banda 1σ no hay ventaja (-0.2 a +1.0 pts, t < 1.2). El efecto solo está en el extremo | Efecto estrecho: solo el extremo -2σ; sin MACD rinde igual |

| 15 oct 2026 | Misma entrada, salida nueva de Manuel: barra bajista que cierra bajo la banda alta del VWAP tras tocarla (X2); la lectura literal X1 se probó solo para comparar | ES 16.8 años | X2: B +3.7 pts netos (t 1.61, +19.7 mil USD, p placebo 0.004), sin MACD +3.5 pts (t 1.89, +32.6 mil, 188 operaciones, p placebo 0.000), A +2.3 (t 0.90). X1 (primera barra roja) pierde: -0.3 a -0.9 pts. Resultado concentrado en 2020, 2024 y 2025; 2023 y 2026 negativos | Candidata débil: pasa el placebo, NO pasa t > 2. Pendiente: réplica en NQ, YM y RTY |
| 15 oct 2026 | Búsqueda honesta de patrones (5,694 reglas de una operación al día: 8 horas x 41 condiciones x largo/corto x 13 salidas), elegir en 2010-18, confirmar en 2019-22, probar en 2023-26, con 30 repeticiones de nulos mezclados | ES 16.8 años | Mejor t en entrenamiento: 2.14 real contra 2.52 de promedio solo por suerte (máx. 3.62). Candidatas que pasan la validación: 0 (por suerte: 0.5 de promedio, máx. 5). Ninguna de las 15 mejores en entrenamiento se sostiene después | Nada: el mejor patrón real no supera lo que da el azar |

## Conclusiones
- En 4.4 años de 0DTE y 16.8 años de ES, ninguna regla intradía probada tiene ventaja después de costos.
- Los niveles de OI/gamma (walls) no aportan información sobre dónde se hace el máximo/mínimo ni mejoran el resultado.
- La gamma estimada con precios de opciones no separa días de reversión de días de tendencia. (No se probó con flujo con signo, que es lo que
  realmente describe la posición de los market makers.)
- Hallazgo estructural verdadero pero sin ventaja operable: el máximo o el mínimo del día cae en la primera hora el 71% de los días
  (34% el máximo, 39% el mínimo); una caminata al azar con volatilidad alta al abrir da ~66%.

- Calibración: al probar ~30 ideas distintas a lo largo del día, un t de ~2 en la mejor es lo que se espera SOLO por suerte (la mejor de 5,694 reglas da t ~ 2.5 con datos sin relación real). Por eso la estrategia de reversión de Manuel (t 1.6 a 1.9 con salida X2) no se puede distinguir del azar.

## Mecánica construida (sirve para cualquier estrategia futura)
Descarga de Theta (historia 0DTE) y de ES por la API de TradeStation; backtest con las mismas reglas que el robot; robot que decide qué haría
(bot/live.py) y envía órdenes al SIMULADOR con stop y objetivo ligados (bot/ts_orders.py, probado: compra, OCO, cancela, cierra).


## Flujo con signo de market makers (en curso, v45)
- Reglas F1-F4 PRE-REGISTRADAS (escritas antes de ver datos) en `bot/flow_eval.py`: F1 sigue la presión de cobertura de 9:30-10:30; F2 la contraria; F3 solo si |P| es alta (mediana de días previos); F4 solo si dealers cortos gamma. Entrada 10:30, salida 15:55 o 12:30, 29 USD/operación, placebo por barajado, 8 pruebas -> |t|>2.7 y 3 tercios con mismo signo.
- Es un PROXY: signo inferido por precio vs bid/ask (Lee-Ready simplificado); el inventario real del dealer no es observable.
- Sin resultados todavía (falta bajar los datos con `bot/flow.py`).
- **Piloto (42 días, 2026-08-14 a 2026-10-13; 60% del volumen clasificado):** F1 -4 USD/op (t -0.02), F2 -54 (t -0.29), F3 +18 (t 0.06, n=15), F4 n=8 (sin datos suficientes). Salida 2 h: igual, nada. Ninguna cumple la barra (|t|>2.7). Con 42 días solo se detectarían efectos de varios cientos de USD por día; el piloto NO descarta efectos pequeños, solo muestra que no hay uno grande y obvio. Siguiente: probar velocidad en días de 2026-01..08 y ampliar.
- Confirmado por Manuel (16-oct): las horas 7:30 y 10:30 de su estrategia son de Nueva York.
- Potencia (SD diaria ~1,200 USD): para |t|>2.7 hace falta un promedio por operación de ~500 USD con 42 días, ~260 con 150, ~185 con 300 y ~120 con 730.

## Estrategia 0DTE de cierre, Etapa 1 (16-oct-2026; ES como sustituto del SPX; 940 días de data_hist)
- Señales de las 15:45 vs movimiento 15:45-16:00 (Z = entre mediana de 20 días previos). Barra pre-registrada: p<0.005 y 3 tercios con el signo previsto.
- RELACIÓN (8 de 10): S1_gex rho -0.11 (mov) / -0.22 (rango); S3_rng +0.25 / +0.53; S5_vol +0.25 / +0.52; S6_imp +0.16 / +0.31. SIN RELACIÓN: S2_dist (distancia a la pared de OI), rho ~0.
- Lectura honesta: S3, S5, S6 son agrupamiento de volatilidad (un día/tramo movido sigue movido) y miden casi lo mismo; el precio de la opción a las 15:45 ya lo descuenta. Que el movimiento sea predecible NO es ventaja: la ventaja exige que lo previsto supere lo que cuesta la prima (Etapa 2). Además los valores p suponen días independientes y hay autocorrelación, así que están exagerados.
- Pared de OI (S2): no predice nada; la hipótesis de "pinning" por distancia a la pared no se sostiene con este dato.
