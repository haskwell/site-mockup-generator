@echo off
setlocal enabledelayedexpansion

echo ========================================================
echo       Building Studio Standalone GUI Installer
echo ========================================================
echo.

where pyinstaller >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] PyInstaller was not found on your PATH or in active environment.
    echo Please run: pip install pyinstaller
    pause
    exit /b 1
)

cd /d "%~dp0\.."

echo [*] Compiling scripts/installer_gui.py into single-file executable...
pyinstaller --noconfirm --onefile --windowed ^
    --name "StudioInstaller" ^
    --icon "assets/studio.ico" ^
    scripts/installer_gui.py

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] PyInstaller compilation failed.
    pause
    exit /b 1
)

echo.
echo ========================================================
echo [SUCCESS] Installer executable compiled!
echo Location: dist\StudioInstaller.exe
echo ========================================================
echo.
pause
