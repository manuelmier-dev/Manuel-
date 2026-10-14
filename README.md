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

## Reglas congeladas y fuera de muestra (14-oct-2026)
Ver `REGLAS.md`. `python -m bot.run_backtest` ahora separa en el reporte lo posterior al 14-oct ("fuera_de_muestra_desde_2026-10-14").
`Params.entry_start` = 9:35 (provisional). `Params.require_rejection` existe pero está en prueba y apagado; `bot.sweep` lo incluye en el mapa.

## Historia con Theta Data (confirmado por su soporte, 14-oct-2026)
- Plan Options Standard de Manuel: opciones SPX a nivel de tick desde 2016 (cotizaciones, operaciones, OHLC, Open Interest, IV y griegas de primer orden).
  La gamma NO viene (es de segundo orden): se calcula con `gamma_from_quotes`. Índice SPX: plan gratis, solo fin de día. ES: Theta no ofrece futuros.
- `bot/theta_snapshot.py` (`summary_from_theta`): del par (cotizaciones de las 9:20, Open Interest) al mismo resumen del día que produce el lector de TradeStation.
  Sin el EM de TradeStation, el EM de referencia es `0.70 x straddle` (`EM_PROXY_FACTOR`; en 30 días reales: error medio 4.4 pts, mediana 8%, correlación 0.78).
- Falta (necesita ejemplos reales de la API): el código que consulta Theta. Ventana recomendada: desde mayo de 2022, cuando las 0DTE pasaron a ser diarias.
- Validación obligatoria antes de usar años: recalcular con Theta los ~40 días que ya se tienen de TradeStation y comparar Open Interest, spot, GEX y walls.
- ES (barras de 5 min con pre-mercado) saldrá de la API de TradeStation (sin costo), no de Theta ni de QuantConnect.

## Descarga de la historia desde Theta (14-oct-2026) — NO PROBADO contra la API real
Investigación (documentación pública de Theta): API REST v3 en `http://127.0.0.1:25503/v3`; Theta Terminal v3 pide Java 21+ y `creds.txt` junto al .jar;
una sola sesión por cuenta e IP fija (errores 476/478); plan Standard con 2 hilos de servidor (una solicitud a la vez);
`/option/at_time/quote` da la última cotización NBBO a la hora pedida (usar horas redondas); el Open Interest lo publica OPRA ~06:30 ET y es el cierre previo.
- `python -m bot.theta_probe`: prueba corta; guarda en `theta_probe/` las respuestas reales (símbolo, expiraciones, cotización y OI, fecha reciente y antigua).
- `python -m bot.theta_download <salida> <desde> <hasta>`: un día por vez, reanuda, registra errores en `theta_errores.csv`, se detiene si hay conflicto de sesión.
- `bot.run_backtest`, `bot.sweep` y `bot.make_journal` aceptan esa carpeta en lugar de la de archivos de TradeStation.
- Correr fuera del horario de mercado, y con un solo Theta Terminal activo.

## Gráficas de estudio y estrategia de tendencia (14-oct-2026)
- `python -m bot.make_study "<cadenas>" "<barras ES>" "<salida>"`: `estudio_dias.pdf` (una página por día), `png/` y `estudio_zonas.csv`.
  Cada gráfica marca con "x" el máximo y mínimo reales del día, los toques a la zona de los walls (con sus confirmaciones), las entradas, las salidas,
  la primera hora, ±1 EM, VWAP y Bollinger. El CSV mide si el máximo/mínimo del día cae cerca del wall (en EM) y si ocurrió en la primera hora.
- `python -m bot.run_trend ...`: prueba de **ruptura del rango de la primera hora** (ORB) en días de gamma negativo. Hipótesis, sin evidencia.
- `Params.second_entry`: "mismo_lado" (regla), "ninguna" o "reversa" (tras un stop, entrar en sentido contrario; diagnóstico para días de ruptura).
