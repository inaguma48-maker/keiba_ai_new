@echo off
chcp 65001 > nul
title JRA Keiba Prediction System Auto Starter

echo ============================================================
echo   JRA Keiba Prediction System - Starting Application
echo ============================================================
echo.

cd /d "%~dp0"

set PORT=5001

echo [1/2] Checking Python dependencies...
python -m pip install -r requirements.txt > nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    python3 -m pip install -r requirements.txt > nul 2>&1
)

echo [2/2] Launching Python Flask Web Server on Port %PORT%...
echo.

start "" "http://localhost:%PORT%"

set PYTHONPATH=%~dp0;%~dp0src;%PYTHONPATH%

python app.py

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Failed to start application using 'python'. Trying 'python3'...
    python3 app.py
)

pause
