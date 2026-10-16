# Opciones SPX 0DTE en los últimos minutos: diseño PRE-REGISTRADO (16-oct-2026)

Todo lo de abajo se escribe ANTES de ver un solo dato de la prueba. Si se cambia algo después, se anota como prueba nueva y se corrige por número de pruebas.
Solo simulador. Hasta que pase la validación, no hay dinero real.

## 0. Qué es dato, qué es estimación, qué es hipótesis
| Tipo | Qué es |
|---|---|
| OBSERVABLE | Precio del SPX/ES, volumen, bid/ask y spread de cada opción, interés abierto (OI) publicado del día anterior, cada operación con su cotización (Theta trade_quote). |
| ESTIMACIÓN | Gamma por strike (modelo Black-Scholes con OI), GEX total, nivel de "gamma flip", strike "imán" (mayor OI/gamma), signo del flujo (precio vs bid/ask) y delta/gamma de los dealers. **El inventario real de los market makers NO se observa.** Se supone: clientes compran calls y puts, dealers del otro lado. |
| HIPÓTESIS (sin validar) | H1: con GEX negativo hay expansión del rango al cierre. H2: con GEX positivo el SPX se queda cerca del strike imán (pinning). H3: cerca de un muro de gamma el movimiento se frena o se acelera. H4: el desbalance de flujo en los últimos 60 min da dirección. H5: el impulso 15:00–15:45 continúa. |

Prior honesto: comprar OTM 0DTE a las 15:45 paga spread + prima de volatilidad. Sin señal, el valor esperado debe ser NEGATIVO. La señal debe vencer ese costo y además repetirse. Un día extraordinario no prueba nada.

## 1. Contexto y señales (todas calculadas con datos disponibles ANTES de 15:45 ET)
- S1 GEX estimado (OI de la mañana × gamma, signo estándar calls +, puts −), y su signo.
- S2 Distancia del spot al strike de mayor |gamma| y al de mayor OI (en puntos y en % del movimiento esperado restante).
- S3 Rango realizado 15:00–15:45 vs rango típico de los 20 días previos (compresión/expansión).
- S4 Desbalance de flujo con signo 15:00–15:45 (proxy): compras de cliente de calls − puts, ponderado por delta.
- S5 Volumen de opciones 0DTE 15:00–15:45 vs mediana de 20 días.
- S6 Impulso: retorno del SPX de 15:00 a 15:45.
Cada señal se divide en terciles con cortes calculados SOLO con días anteriores (sin mirar el futuro).

## 2. Entrada (una sola operación por día)
- Hora: 15:45 ET (ask de ese momento). Variante: 15:30.
- Dirección: regla D1 = hacia el lado de S4 si |S4| está en el tercil alto y concuerda con el signo de S6; regla D2 = solo S6. Sin acuerdo: no se opera. (Dos reglas, no más.)
- Condición de "expansión" para operar: S1 < 0 (o S3 en tercil alto). Si no, abstenerse.
- Strike: el OTM más cercano a una distancia de 0.20% del spot (~15 puntos) en la dirección. Variante: 0.10%.

## 3. Selección del contrato (filtros duros)
- bid > 0; ask entre 0.30 y 3.00 USD; spread (ask−bid) ≤ 0.10 USD o ≤ 25% del ask, el menor.
- Cotización con menos de 60 s de antigüedad; tamaño en ask ≥ 5.
- Si ningún strike cumple: no se opera.

## 4. Riesgo y salidas
- 1 contrato (paper). Pérdida máxima = prima pagada (≤ 300 USD). Máximo 1 operación/día; si hay 5 pérdidas seguidas, se detiene y se revisa.
- Salida A: mantener hasta el vencimiento (valor intrínseco a 16:00). Salida B: vender al bid cuando valga 3× la prima, o a las 15:55 al bid, lo que pase primero. Nunca después de 15:57.

## 5. Abstención (no se opera)
Spread ancho; bid = 0; cotización vieja; falta de datos de OI o de operaciones; días con evento fuerte a las 14:00–16:00 (FOMC, cierres especiales, medio día de mercado); salto > 1% del SPX en los 15 min previos (el movimiento ya ocurrió); señal contradictoria; fallo de Theta.

## 6. Validación (en orden; si falla una, se detiene)
Datos: ~2022-05 a 2026-10 (~900 días de 0DTE). Cortes: entrenamiento 50% / validación 25% / prueba 25% en orden cronológico; la prueba se abre UNA vez.
- **Etapa 1 (barata, sin precios de opciones):** ¿las señales S1–S3, S5 predicen el rango del SPX/ES entre 15:45 y 16:00 (|movimiento|, tercil)? Compara contra un placebo (señales barajadas entre días). Si no hay relación, se acaba aquí: no hay motivo para comprar nada.
- **Etapa 2 (P&L realista):** instantáneas at_time de cotizaciones a las 15:45, 15:55 y al vencimiento. Entrada al ASK, salida B al BID, comisión 0.65 USD por lado, +0.05 de deslizamiento, y los vencidos sin valor cuentan como −prima. Regla A y B, D1 y D2, 0.10% y 0.20%, 15:30 y 15:45: 16 combinaciones → exige p < 0.05/16 y los 3 periodos con el mismo signo.
- **Línea base obligatoria:** comprar SIEMPRE call+put OTM a las 15:45 sin señal. Se espera negativa. Si la estrategia no la supera con claridad, no tiene valor.
- **Placebo:** mismas operaciones con la dirección al azar y con días barajados (2,000 veces).
- **Colas:** como los pagos son muy asimétricos, se reporta media, mediana, intervalo bootstrap, resultado SIN los 5 mejores días y número de días ganadores. Si el total depende de 3 días, es suerte.
- **Mínimo:** ≥ 200 operaciones, de lo contrario "sin conclusión".
- **Tamaño del efecto detectable:** se informa antes de mirar el resultado.

## 7. Qué se necesita y cuándo
- Etapa 1: tablas de OI/gamma que ya están en el servidor (data_hist/data_val) + barras de ES de 5 min. Sin Theta nuevo.
- Etapa 2: instantáneas de cotizaciones a 15:45/15:55/vencimiento. Cada una es rápida, similar a la de las 9:20.
- Flujo con signo de 15:00–15:45: es una descarga nueva de trade_quote. Theta solo admite una sesión: **no se puede lanzar mientras corre la ampliación de la primera hora** (termina esta noche).
