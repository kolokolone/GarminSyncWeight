param()
$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$Root = Split-Path -Parent $PSScriptRoot
$Runtime = Join-Path $Root "runtime"
New-Item -ItemType Directory -Force -Path $Runtime | Out-Null

Write-Host "=== GarminSyncWeight Dev Server ===" -ForegroundColor Cyan
Write-Host "Démarrage du backend sur http://127.0.0.1:8010" -ForegroundColor Yellow
Write-Host "Arrêt: Ctrl+C" -ForegroundColor Yellow

$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONPATH = Join-Path $Root "backend"
$Python = Join-Path $Root ".venv\Scripts\python.exe"

if (Test-Path -LiteralPath $Python) {
    & $Python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8010 --reload
} elseif (Get-Command uv -ErrorAction SilentlyContinue) {
    uv run python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8010 --reload
} else {
    throw ".venv introuvable et uv est introuvable. Lancez d'abord: uv sync"
}
