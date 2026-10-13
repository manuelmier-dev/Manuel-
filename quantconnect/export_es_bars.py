"""Cuaderno de QuantConnect Research: exporta barras de ES de 5 minutos con pre-mercado a CSV.

*** NO PROBADO: se ejecuta dentro de QuantConnect, no en este repositorio. Si algún nombre cambió
*** en tu versión de LEAN, el error dirá cuál; se ajusta en minutos.

Cómo usarlo: en QuantConnect abre un proyecto de Research (cuaderno), pega esto en una celda y ejecútala.
Las barras salen con la hora de Nueva York (así las espera bot.validate) y precios SIN ajustar (Raw),
para que la base ES - SPX de cada día sea correcta.
"""
from datetime import datetime

import pandas as pd

START, END = datetime(2026, 8, 1), datetime(2026, 10, 14)   # cambia el rango si hace falta

qb = QuantBook()  # noqa: F821  (existe dentro de QuantConnect)
es = qb.AddFuture(  # noqa: F821
    Futures.Indices.SP500EMini, Resolution.Minute,  # noqa: F821
    dataNormalizationMode=DataNormalizationMode.Raw,  # noqa: F821
    dataMappingMode=DataMappingMode.OpenInterest,  # noqa: F821
    contractDepthOffset=0, extendedMarketHours=True)

h = qb.History(es.Symbol, START, END, Resolution.Minute, extendedMarketHours=True)  # noqa: F821
bars = h.reset_index()
time_col = "time" if "time" in bars.columns else bars.columns[1]
bars[time_col] = (pd.to_datetime(bars[time_col]).dt.tz_localize("America/Chicago", ambiguous="NaT", nonexistent="NaT")
                  .dt.tz_convert("America/New_York"))
bars = bars.dropna(subset=[time_col]).set_index(time_col).sort_index()

five = bars.resample("5min", label="left", closed="left").agg(
    {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna()
print(five.head(), "\n", five.tail(), "\n", len(five), "barras")
qb.ObjectStore.Save("es_5min.csv", five.to_csv())  # noqa: F821  (se descarga desde el Object Store)
