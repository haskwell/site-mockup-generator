@echo off
setlocal
cd /d "%~dp0"

REM Launch PowerShell GUI Installer without elevating or requiring Admin rights
powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "%~dp0installer.ps1"

if %errorlevel% neq 0 (
    echo.
    echo If the installer window did not appear, PowerShell may be restricted.
    echo Retrying in interactive console mode...
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0installer.ps1"
    pause
)
