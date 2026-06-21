param()
$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$Root = Split-Path -Parent $PSScriptRoot

Write-Host "=== GarminSyncWeight ===" -ForegroundColor Cyan
Write-Host "Backend: http://127.0.0.1:8010" -ForegroundColor Green
Write-Host "Docs:    http://127.0.0.1:8010/docs" -ForegroundColor Green

$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONPATH = Join-Path $Root "backend"
$Python = Join-Path $Root ".venv\Scripts\python.exe"

if (Test-Path -LiteralPath $Python) {
    & $Python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8010
} elseif (Get-Command uv -ErrorAction SilentlyContinue) {
    uv run python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8010
} else {
    throw ".venv introuvable et uv est introuvable. Lancez d'abord: uv sync"
}
