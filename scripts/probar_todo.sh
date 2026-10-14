#!/usr/bin/env bash
# Prueba todo en un solo paso, en el droplet de pruebas.
#   Uso:  bash /root/probar_todo.sh
# Necesita en /root:  bot-fase1.zip  (y, para el backtest: ES_5min.csv y la carpeta cadenas/)
# No borra nada fuera de la carpeta bot-fase1 ni toca otros servidores.
BASE="${BASE:-/root}"
cd "$BASE" || exit 1

echo "== 1/5 Código"
[ -f bot-fase1.zip ] || { echo "FALTA $BASE/bot-fase1.zip (súbelo con scp)"; exit 1; }
rm -rf bot-fase1 && python3 -m zipfile -e bot-fase1.zip . || { echo "No pude descomprimir el ZIP"; exit 1; }
cd bot-fase1 || exit 1

echo "== 2/5 Python"
if [ ! -d "$BASE/venv_bot" ]; then
  python3 -m venv "$BASE/venv_bot" 2>/dev/null || { apt-get update -q >/dev/null && apt-get install -y -q python3-venv >/dev/null && python3 -m venv "$BASE/venv_bot"; } || { echo "No pude crear el entorno de Python"; exit 1; }
fi
. "$BASE/venv_bot/bin/activate"
pip install -q -r requirements.txt || { echo "Falló pip install"; exit 1; }

echo "== 3/5 Pruebas (deben decir OK)"
python -m unittest discover -s tests 2>&1 | tail -4
echo "   (si dice menos de 34 pruebas, el ZIP de Dropbox es viejo)"

if [ -f "$BASE/ES_5min.csv" ] && [ -d "$BASE/cadenas" ]; then
  echo "== 4/5 Backtest"
  python -m bot.run_backtest "$BASE/cadenas" "$BASE/ES_5min.csv" "$BASE/operaciones.csv" 2>&1 | tail -60
  echo "== 5/5 Bitácora"
  python -m bot.make_journal "$BASE/cadenas" "$BASE/ES_5min.csv" "$BASE/bitacora.csv" 2>&1 | tail -25
else
  [ -f "$BASE/ES_5min.csv" ] || echo "== AVISO: falta $BASE/ES_5min.csv (las barras de ES). Sin ellas no hay backtest."
  [ -d "$BASE/cadenas" ] || echo "== AVISO: falta la carpeta $BASE/cadenas"
  echo "== 4/5 y 5/5 omitidos. Resumen de cadenas sin barras de ES:"
  [ -d "$BASE/cadenas" ] && python -m bot.inspect_chains "$BASE/cadenas" "$BASE/resumen_cadenas.csv" 2>&1 | tail -15
fi
mkdir -p "$BASE/resultados"
for f in operaciones bitacora resumen_cadenas comparacion_walls; do [ -f "$BASE/$f.csv" ] && cp -f "$BASE/$f.csv" "$BASE/resultados/"; done
[ -f "$BASE/reporte_backtest.json" ] && cp -f "$BASE/reporte_backtest.json" "$BASE/resultados/"
echo "== Resultados guardados en $BASE/resultados (se bajan solos a Dropbox con subir_y_probar.ps1)"
echo "== Fin. Mándame la captura de esta pantalla."
