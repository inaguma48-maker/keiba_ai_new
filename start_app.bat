@echo off
chcp 65001 > nul
title JRA Keiba Prediction System Auto Starter

echo ============================================================
echo   JRA Keiba Prediction System - Starting Application
echo ============================================================
echo.

cd /d "%~dp0"

set PORT=5001

echo [1/2] Launching Python Flask Web Server on Port %PORT%...
echo.

start "" "http://localhost:%PORT%"

python app.py

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Failed to start application using 'python'. Trying 'python3'...
    python3 app.py
)

pause
