@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo === GarminSyncWeight ===
echo Admin local: http://127.0.0.1:8010
echo API docs:    http://127.0.0.1:8010/docs
echo.

where uv >nul 2>nul
if errorlevel 1 (
    echo [ERREUR] uv est introuvable. Installez uv ou ajoutez-le au PATH.
    echo.
    pause
    exit /b 1
)

set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

uv run uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8010

set "EXIT_CODE=%ERRORLEVEL%"
echo.
if not "%EXIT_CODE%"=="0" (
    echo [ERREUR] GarminSyncWeight s'est arrete avec le code %EXIT_CODE%.
) else (
    echo GarminSyncWeight s'est arrete normalement.
)
echo.
pause
exit /b %EXIT_CODE%
