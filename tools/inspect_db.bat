@echo off
rem Drag a SQLite .db file onto this file. It writes db_structure.txt (table/column names only) and opens it.
if "%~1"=="" (
  echo Drag and drop your .db file onto this file.
  pause
  exit /b 1
)
set PYTHONIOENCODING=utf-8
set PYEXE=python
where python >nul 2>&1 || set PYEXE=py
"%PYEXE%" "%~dp0tools\inspect_db.py" "%~1" --rows 0 > "%~dp0db_structure.txt" 2>&1
if errorlevel 1 (
  echo Failed. Is Python installed? See db_structure.txt
)
start notepad "%~dp0db_structure.txt"
