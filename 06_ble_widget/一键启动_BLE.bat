@echo off
title ESP32 BLE 发射器 (G-Helper 协同版)

:: 检查管理员权限，若无则通过 PowerShell 请求 UAC 提权
net session >nul 2>&1
if %errorLevel% NEQ 0 (
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

cd /d "%~dp0"
echo ========================================================
echo   ESP32 华硕笔记本副屏 - BLE 发射器 (G-Helper 协同版)
echo ========================================================
echo.

python ble_pc_sender.py

pause
