@echo off
setlocal enabledelayedexpansion

echo ========================================================
echo       Package Studio Release Package for Local Testing
echo ========================================================
echo.

cd /d "%~dp0"

REM Step 1: Build the Studio application executable if not already built
if not exist "dist\Studio\Studio.exe" (
    echo [*] Executable not found in dist\Studio. Running build_exe.bat...
    call build_exe.bat
    if %errorlevel% neq 0 (
        echo [ERROR] Application build failed.
        pause
        exit /b 1
    )
) else (
    echo [*] Found existing build at dist\Studio\Studio.exe
)

REM Step 2: Copy .env.example into dist\Studio if present
if exist ".env.example" (
    copy /y ".env.example" "dist\Studio\.env.example" >nul 2>nul
)

REM Step 3: Compress dist\Studio into Studio-Windows-x64.zip
echo.
echo [*] Compressing dist\Studio into dist\Studio-Windows-x64.zip...
powershell -NoProfile -Command "Compress-Archive -Path 'dist\Studio\*' -DestinationPath 'dist\Studio-Windows-x64.zip' -Force"

if %errorlevel% neq 0 (
    echo [ERROR] Compression failed.
    pause
    exit /b 1
)

echo.
echo ========================================================
echo [SUCCESS] Release package created:
echo    dist\Studio-Windows-x64.zip
echo.
echo You can now run 'Studio-Installer.bat' or 'scripts\installer_gui.py'.
echo The installer will automatically detect this local zip file,
echo allowing you to test installation, updates, desktop shortcuts,
echo and .env preservation offline on this machine!
echo ========================================================
echo.
pause
