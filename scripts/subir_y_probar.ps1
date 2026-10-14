# subir_y_probar.ps1 -- funciona en cualquier computadora con Dropbox (busca solo la carpeta de Dropbox).
# *** NO PROBADO en Windows: Claude no tiene Windows. Si da error, manda la captura y se corrige.
#
# Uso (PowerShell, ventana azul):   .\subir_y_probar.ps1        o        .\subir_y_probar.ps1 -Servidor 1.2.3.4
# Carpetas de Dropbox que usa (con tus nombres actuales):
#   Dropbox\Bot Claude\                         bot-fase1.zip, probar_todo.sh, ES_5min.csv (opcional)
#   Dropbox\Bot SPX ES\Cadenas SPX 0DTE\        las cadenas .xls de cada día
#   Dropbox\Bot Claude\resultados\              aquí regresan operaciones.csv, bitacora.csv, etc.
# NUNCA pongas claves, contraseñas, .env ni config.ini en Dropbox: se copian a todas tus computadoras.
param([string]$Servidor = "178.128.71.99")

# 1) Encontrar Dropbox, esté donde esté en esta computadora
$Dropbox = $null
foreach ($f in @("$env:LOCALAPPDATA\Dropbox\info.json", "$env:APPDATA\Dropbox\info.json")) {
    if (Test-Path $f) {
        $info = Get-Content $f -Raw | ConvertFrom-Json
        if ($info.personal) { $Dropbox = $info.personal.path } elseif ($info.business) { $Dropbox = $info.business.path }
        break
    }
}
if (-not $Dropbox) { $Dropbox = Join-Path $env:USERPROFILE "Dropbox" }
Write-Host "Dropbox en: $Dropbox"

$Carpeta = Join-Path $Dropbox "Bot Claude"
$Cadenas = Join-Path $Dropbox "Bot SPX ES\Cadenas SPX 0DTE"
$Zip     = Join-Path $Carpeta "bot-fase1.zip"
$Script  = Join-Path $Carpeta "probar_todo.sh"
$Barras  = Join-Path $Carpeta "ES_5min.csv"

$faltan = $false
foreach ($a in @($Zip, $Script, $Cadenas)) {
    if (-not (Test-Path $a)) { Write-Host "FALTA: $a" -ForegroundColor Red; $faltan = $true }
}
if ($faltan) { exit 1 }
$Subir = @($Zip, $Script)
if (Test-Path $Barras) { $Subir += $Barras } else { Write-Host "Aviso: no hay ES_5min.csv; se probará sin barras de ES" -ForegroundColor Yellow }

$Destino = "root@$Servidor"
Write-Host "1/5 Limpiando la carpeta de cadenas del servidor de pruebas (pide la contraseña)"
ssh $Destino "rm -rf /root/cadenas && mkdir -p /root/cadenas"
Write-Host "2/5 Subiendo código y barras"
scp $Subir "${Destino}:/root/"
Write-Host "3/5 Subiendo cadenas"
scp -r $Cadenas "${Destino}:/root/cadenas/"
Write-Host "4/5 Probando en el servidor"
ssh $Destino "bash /root/probar_todo.sh"
Write-Host "5/5 Trayendo los resultados a Dropbox"
scp -r "${Destino}:/root/resultados" $Carpeta
Write-Host "Listo. Resultados en: $(Join-Path $Carpeta 'resultados')" -ForegroundColor Green
