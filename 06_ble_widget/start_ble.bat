@echo off
title ESP32 BLE Sender (G-Helper & FPS)

:: Check administrator privileges, request UAC elevation if needed
net session >nul 2>&1
if %errorLevel% NEQ 0 (
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

cd /d "%~dp0"
echo ========================================================
echo   ESP32 ASUS Laptop Dashboard - BLE Sender (FPS Enhanced)
echo ========================================================
echo.

taskkill /f /im EtwFpsHelper.exe >nul 2>&1
if exist "tools\bin\EtwFpsHelper.exe" (
    start "" /b "tools\bin\EtwFpsHelper.exe"
)

python ble_pc_sender.py

taskkill /f /im EtwFpsHelper.exe >nul 2>&1
pause
