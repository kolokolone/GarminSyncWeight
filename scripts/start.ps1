param()
$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$Root = Split-Path -Parent $PSScriptRoot

function Require-Command($Name) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Commande requise introuvable: $Name"
    }
}

Require-Command "uv"

Write-Host "=== GarminSyncWeight ===" -ForegroundColor Cyan
Write-Host "Backend: http://127.0.0.1:8010" -ForegroundColor Green
Write-Host "Docs:    http://127.0.0.1:8010/docs" -ForegroundColor Green

uv run uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8010
