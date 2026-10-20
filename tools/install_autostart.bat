@echo off
rem Copies the app to %USERPROFILE%\keiba_app and starts it at every Windows logon (hidden, no console).
setlocal
for %%I in ("%~dp0..") do set "SRC=%%~fI"
set "DEST=%USERPROFILE%\keiba_app"
set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "PYW="
for /f "delims=" %%i in ('where pythonw 2^>nul') do if not defined PYW set "PYW=%%i"
if not defined PYW (
  echo pythonw.exe was not found. Install Python and tick "Add python.exe to PATH".
  pause
  exit /b 1
)
echo Copying the app to "%DEST%" ...
robocopy "%SRC%" "%DEST%" /E /XD .git data models __pycache__ /XF racing_app.db >nul
if errorlevel 8 (
  echo Copy failed.
  pause
  exit /b 1
)
echo Installing the libraries (first time only) ...
python -m pip install -q -r "%DEST%\requirements.txt"
echo Registering the startup entry ...
echo CreateObject("Wscript.Shell").Run """%PYW%"" ""%DEST%\app.py""", 0, False > "%STARTUP%\keiba_viewer.vbs"
powershell -NoProfile -Command "$d=[Environment]::GetFolderPath('Desktop'); Set-Content -Path (Join-Path $d 'keiba-viewer.url') -Value @('[InternetShortcut]','URL=http://localhost:5000')"
echo Starting the app now ...
wscript "%STARTUP%\keiba_viewer.vbs"
echo.
echo Done. Open http://localhost:5000 (a shortcut "keiba-viewer" was put on the Desktop).
echo From now on the app starts by itself when you log in to Windows.
pause
