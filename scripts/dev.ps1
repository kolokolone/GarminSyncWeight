param()
$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$Root = Split-Path -Parent $PSScriptRoot
$Runtime = Join-Path $Root "runtime"
New-Item -ItemType Directory -Force -Path $Runtime | Out-Null

function Require-Command($Name) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Commande requise introuvable: $Name"
    }
}

Require-Command "uv"

Write-Host "=== GarminSyncWeight Dev Server ===" -ForegroundColor Cyan
Write-Host "Démarrage du backend sur http://127.0.0.1:8010" -ForegroundColor Yellow
Write-Host "Arrêt: Ctrl+C" -ForegroundColor Yellow

uv run uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8010 --reload
