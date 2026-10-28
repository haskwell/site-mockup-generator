@echo off
setlocal enabledelayedexpansion

echo ========================================================
echo       Building Studio Portable Windows Executable
echo ========================================================
echo.

REM 1. Check for Python
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Python was not found on your PATH.
    echo Please install Python 3.10+ from python.org and check "Add python.exe to PATH".
    pause
    exit /b 1
)

REM 2. Create/Activate virtual environment
if not exist ".venv" (
    echo [*] Creating virtual environment (.venv)...
    python -m venv .venv
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
)

call .venv\Scripts\activate.bat

REM 3. Install requirements and PyInstaller
echo [*] Installing dependencies and PyInstaller...
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install pyinstaller

REM 4. Clean previous builds
if exist "build" rmdir /s /q "build"
if exist "dist" rmdir /s /q "dist"

REM 5. Run PyInstaller
echo.
echo [*] Compiling Studio.exe...
pyinstaller studio.spec --clean --noconfirm
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] PyInstaller build failed. Check the error messages above.
    pause
    exit /b 1
)

echo.
echo ========================================================
echo [SUCCESS] Build complete!
echo Your standalone executable is located at:
echo    dist\Studio.exe
echo ========================================================
echo.
pause
