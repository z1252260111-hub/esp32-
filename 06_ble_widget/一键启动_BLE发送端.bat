@echo off
chcp 65001 >nul
title ESP32 BLE 发射器 (G-Helper & FPS 增强版)

>nul 2>&1 "%SYSTEMROOT%\system32\cacls.exe" "%SYSTEMROOT%\system32\config\system"
if '%errorlevel%' NEQ '0' (
    echo [提示] 正在请求管理员权限以开启华硕硬件直读与游戏 FPS 监控...
    goto UACPrompt
) else ( goto gotAdmin )

:UACPrompt
    echo Set UAC = CreateObject^("Shell.Application"^) > "%temp%\getadmin.vbs"
    echo UAC.ShellExecute "%~s0", "", "", "runas", 1 >> "%temp%\getadmin.vbs"
    "%temp%\getadmin.vbs"
    exit /B

:gotAdmin
    if exist "%temp%\getadmin.vbs" ( del "%temp%\getadmin.vbs" )
    cd /d "%~dp0"

echo ========================================================
echo   ESP32 华硕笔记本副屏 - BLE 发射器 (G-Helper ^& FPS)
echo ========================================================
echo.

python ble_pc_sender.py

pause
