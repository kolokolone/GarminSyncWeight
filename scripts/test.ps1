param()
$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$Root = Split-Path -Parent $PSScriptRoot

Write-Host "=== GarminSyncWeight Tests ===" -ForegroundColor Cyan

Write-Host "`n[1/2] Ruff lint check..." -ForegroundColor Yellow
uv run ruff check backend
if ($?) { Write-Host "  ✓ Lint OK" -ForegroundColor Green }

Write-Host "`n[2/2] Pytest..." -ForegroundColor Yellow
uv run pytest -v
if ($?) { Write-Host "  ✓ Tests OK" -ForegroundColor Green }

Write-Host "`n=== All checks passed ===" -ForegroundColor Green
