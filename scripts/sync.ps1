param(
    [string]$StartDate,
    [string]$EndDate
)
$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$Root = Split-Path -Parent $PSScriptRoot

if (-not $StartDate -or -not $EndDate) {
    Write-Host "Usage: .\scripts\sync.ps1 -StartDate 2026-06-01 -EndDate 2026-06-19" -ForegroundColor Yellow
    exit 1
}

Write-Host "=== GarminSyncWeight Sync ===" -ForegroundColor Cyan
Write-Host "  Période: $StartDate → $EndDate" -ForegroundColor White

uv run python -m backend.app.cli sync --start-date $StartDate --end-date $EndDate
