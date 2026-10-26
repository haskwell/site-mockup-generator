@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0launch-setup.ps1" %*
pause