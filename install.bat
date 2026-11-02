@echo off
setlocal
cd /d "%~dp0"

echo Launching Studio Installer...
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1"

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Installation encountered an issue. See messages above.
    pause
)
