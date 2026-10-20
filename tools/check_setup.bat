@echo off
rem Double-click: runs the self-check and opens the result in Notepad.
set PYTHONIOENCODING=utf-8
set PYEXE=python
where python >nul 2>&1 || set PYEXE=py
"%PYEXE%" "%~dp0check_setup.py" > "%~dp0check_result.txt" 2>&1
start notepad "%~dp0check_result.txt"
