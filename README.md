# Bot de ES con gamma de SPX 0DTE

Fase 1: cálculo de GEX/walls/movimiento esperado y backtest. **No opera con dinero.**

## Reglas implementadas (de Manuel)
- Se opera solo si el GEX total es **positivo** y el movimiento esperado (EM) ≥ **20** pts.
  La banda de ±0.5 se descartó (Manuel, 13-oct); sigue disponible con `Params(gex_min=0.5)`.
  Gamma negativo = día de tendencia: se registra como `gamma_negativo_tendencia` y no se opera, porque
  requiere otra estrategia (fase posterior). Primero se prueba la reversión a la media en los días de gamma positivo.
- Zona: wall de gamma (call wall → corto, put wall → largo), entre 9:30 y 10:30 NY.
- Confirmación: al menos **2 de 3** (VWAP ±2σ, Bollinger 20/2, RSI 14 en 70/30). Ajustable en `bot/config.py`.
- Salida: 90% del EM o el wall contrario (lo que llegue primero). Stop: 20% del EM.
- 1 entrada al día; una 2a solo después de un stop y con confirmaciones nuevas (máx. 2).

## Supuestos que hay que revisar
- EM = straddle ATM 0DTE en puntos (movimiento hacia un lado desde la apertura).
- Walls en strikes SPX → se pasan a ES sumando la base (ES − SPX) del día.
- Señal al cierre de una barra; entrada en la apertura de la siguiente. Si stop y objetivo caen en la misma barra, se asume stop.
- Cierre forzado 15:55 NY; 2a entrada hasta 11:30 NY; comisión 4 USD y 0.25 pt de deslizamiento por lado.
- GEX con Open Interest del día anterior (aproximación: market makers largos en calls, cortos en puts).
  Para 0DTE, buena parte del interés abre el mismo día, así que esta medida puede ser débil. Hay que medirlo.

## Formato de datos (lo que debe entregar el código de bajada)
**Barras de ES (5 min)**: índice fecha-hora con zona `America/New_York`; columnas `open, high, low, close, volume`.

**Días** (índice = fecha operada): `gex_bn, em_pts, call_wall, put_wall, basis, oi_date`.
`oi_date` debe ser **anterior** a la fecha operada; si no, el backtest se detiene (protección contra mirar el futuro).

## Probar
```
python -m unittest discover -s tests -v
```
Claves y datos nunca van al repositorio (`.env` y `data/` están ignorados).

## Cadenas SPX 0DTE de TradeStation (.xls)
`python -m bot.inspect_chains "<carpeta con los .xls>" [salida.csv]` lee todos los archivos y resume cada día:
precio del SPX (por paridad put-call), movimiento esperado (straddle **y** el de TradeStation), GEX total y walls
(por GEX y por Open Interest). No decide nada: muestra las alternativas para elegir con datos.
Límites vistos en el archivo real: solo ~30 strikes (±70 pts), gamma redondeada a 3 decimales, sin precio del índice ni de ES.

## Tabla de días y decisiones de Manuel (13-oct-2026)
- Movimiento esperado = el de TradeStation (encabezado del archivo); si falta, el straddle.
- Wall inicial = mayor Open Interest.
- `bot.days.build_days(resumen, barras_ES)` arma la tabla del backtest. Las barras de ES deben incluir pre-mercado
  (la base ES − SPX se toma a las 9:20 NY). RSI y Bollinger se calculan sobre todas las barras; el VWAP arranca a las 9:30.
- Filtro de gamma (solo signo por defecto): `Params.gex_metric` = `"bn"` (mil millones, tal cual) o `"ratio"` (neto/total, entre -1 y 1). **Por confirmar.**
  Ejemplo real: el 13-oct el GEX fue +8.08 mil millones (pasa el filtro) pero la proporción fue 0.21 (queda en zona "choppy").
- `quantconnect/export_es_bars.py`: borrador (no probado) para sacar las barras de ES desde QuantConnect.

## Bitácora diaria (una fila por día, opere o no)
`python -m bot.make_journal "<carpeta de cadenas>" [barras_es.csv|-] [bitacora.csv]`
- Antes de la apertura: régimen (`reversion` si GEX > 0, `tendencia` si no), gamma, EM, walls, si el bot opera y por qué no.
- Después del cierre (con barras de ES de 5 min con zona NY): rango, movimiento, hora del máximo y mínimo, y si caen entre 9:30 y 10:30.
- Imprime la prueba de la observación de Manuel (máximo o mínimo entre 9:30 y 10:30) y compara los dos regímenes.
- Una sesión con menos de 70 barras se ignora, para no mezclar días incompletos.
- Programarlo a diario (cron) depende de de dónde salgan las barras de ES; por eso aún no está programado.

## Barras de ES desde TradeStation (EasyLanguage)
`tradestation/ExportBarras5min.txt` (NO PROBADO en TradeStation): indicador que escribe cada barra de la gráfica en `C:\TS_Export\ES_5min.csv`.
- Gráfica de `@ES` a 5 min, con horario extendido, del 1-ago-2026 a hoy. Crear antes la carpeta `C:\TS_Export`.
- TradeStation numera las barras por hora de **cierre** y la fecha como `1261013` (13-oct-2026). `bot/tsbars.py` lo convierte a hora de inicio, zona Nueva York.
- Comprueba la zona horaria con el volumen (la barra de las 9:30 debe ser la de más volumen en ≥ 50% de los días) y descarta días con base ES−SPX fuera de [-30, 150] pts (señal de precios ajustados).

## Backtest completo
`python -m bot.run_backtest "<carpeta de cadenas>" "<barras de ES .csv>" [operaciones.csv]`
Con pocos días no concluye nada; sirve para encontrar errores y ver el comportamiento por primera y segunda entrada.

## Formatos de cadena y regla de la hora (14-oct-2026)
- Formato completo (sept. en adelante, `.xls` o `.csv`): trae gamma. Formato de agosto: sin símbolo ni gamma; la gamma se
  estima de los precios (`bot.gex.gamma_from_quotes`). Validación contra archivos que sí traen gamma: mediana del cociente
  1.00 (0.89 a 1.14 cerca del precio); el GEX total difiere entre 7% y 16%, el signo coincide.
- La hora del nombre del archivo (`7.20am`) se toma como hora de **Mérida** y se pasa a Nueva York (`NAME_TZ` en `bot/loaders.py`).
  Un archivo exportado después de las 9:30 NY se rechaza (los precios ya no son de antes de la apertura).
- Si hay dos archivos del mismo día, queda el más tardío que sea válido (anterior a la apertura).
- Se descartan las filas basura al final de los archivos de agosto (la delta del call no puede subir al alejarse del precio).

## Definición de wall y ancho de la cadena (14-oct-2026)
- Manuel: "lo que consideres más conveniente". Por defecto el wall de entrada es el **mayor Open Interest dentro de ±1 EM del precio**
  (calls entre el precio y +1 EM; puts entre -1 EM y el precio). Motivo: con el mayor OI de todo el archivo, el wall quedaba en promedio
  a 1.4 EM (call) y 1.9 EM (put), casi siempre fuera del rango del día. `python -m bot.run_backtest` compara las tres definiciones
  (`oi`, `oi_1em`, `gex`) lado a lado.
- Si un lado no tiene wall (OI cero en el rango), ese lado no genera entradas y el objetivo es solo el 90% del EM.
- Desde el 15-oct Manuel exportará todos los strikes. Para comparar con los archivos viejos, el GEX (`gex_bn`, `gex_ratio`) se calcula con los
  strikes a ±90 pts del precio (todos los archivos viejos caben en esa ventana, así que sus valores no cambian); `gex_bn_total` usa todos los strikes del archivo.

## Corrección importante: el spot de las 9:20 es el cierre del día anterior (14-oct-2026)
La cadena de las 9:20 trae precios de antes de abrir: el "spot" por paridad coincide con el cierre previo (correlación 0.94 con el
cierre de ES del día anterior, contra 0.85 con la apertura). Por eso la primera versión del backtest alineaba mal los walls con ES
(error de ±34 pts, la desviación del salto nocturno, más de 1 EM).
- `bot/days.py`: base ES-SPX (`carry`) = cierre de ES del día anterior - spot del archivo, con mediana móvil de 5 días.
  Precio real a las 9:20 en coordenadas SPX = ES(9:15) - carry. Los walls "±1 EM" se buscan alrededor de ese precio.
- `python -m bot.sweep`: mapa de sensibilidad (stop, objetivo, confirmaciones, hora de inicio, wall). Diagnóstico, no para elegir el "mejor".
- Diagnóstico de la primera corrida (con la alineación vieja): 11 de 19 stops cayeron en la misma barra de la entrada;
  las 6 entradas de las 9:35 perdieron todas. Hipótesis por probar, no regla.
