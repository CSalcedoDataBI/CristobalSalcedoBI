<#
.SYNOPSIS
    Abre el reporte de telemetria en local, con los datos mas recientes.

.DESCRIPTION
    Sirve docs/ en un puerto local y abre el navegador. Nada sale de la maquina:
    el dashboard lee los JSON del disco, no de internet.

    Antes de servir hace 'git pull' para traer el snapshot que el cron commiteo
    esta madrugada. Si no hay red, sigue adelante con lo que ya haya en disco:
    ver datos de ayer es mejor que no ver nada.

.PARAMETER Port
    Puerto local. Por defecto 8899.

.PARAMETER NoPull
    No intenta actualizar desde GitHub. Util sin conexion.
#>
[CmdletBinding()]
param(
    [int]$Port = 8899,
    [switch]$NoPull
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$docs = Join-Path $repo 'docs'

if (-not (Test-Path (Join-Path $docs 'index.html'))) {
    Write-Host "No encuentro docs/index.html en $repo" -ForegroundColor Red
    Read-Host "Enter para cerrar"; exit 1
}

Write-Host "=== Telemetria del portafolio ===" -ForegroundColor Cyan

if (-not $NoPull) {
    Write-Host "  Actualizando datos..." -NoNewline
    try {
        git -C $repo pull --ff-only --quiet 2>&1 | Out-Null
        Write-Host " OK" -ForegroundColor Green
    } catch {
        Write-Host " sin red, uso los datos que ya tengo" -ForegroundColor Yellow
    }
}

# Fecha del ultimo snapshot, para saber de un vistazo si el cron corrio.
$summary = Join-Path $docs 'telemetry\summary.json'
if (Test-Path $summary) {
    $s = Get-Content $summary -Raw | ConvertFrom-Json
    $edad = (New-TimeSpan -Start ([datetime]$s.snapshot_date) -End (Get-Date)).Days
    $color = if ($edad -le 2) { 'Green' } else { 'Yellow' }
    Write-Host "  Ultimo snapshot: $($s.snapshot_date) (hace $edad dia(s))" -ForegroundColor $color
    if ($edad -gt 2) {
        Write-Host "  El cron diario puede estar fallando - revisa la pestana Actions." -ForegroundColor Yellow
    }
}

# Si el puerto ya esta ocupado, es que ya lo tienes abierto: reusa esa instancia.
$ocupado = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($ocupado) {
    Write-Host "  Ya habia un servidor en :$Port, reuso ese." -ForegroundColor DarkGray
    Start-Process "http://localhost:$Port/"
    exit 0
}

Write-Host "  Sirviendo en http://localhost:$Port/  (Ctrl+C para cerrar)" -ForegroundColor Cyan
Start-Process "http://localhost:$Port/"
python -m http.server $Port --directory $docs --bind 127.0.0.1
