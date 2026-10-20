@echo off
rem One-click setup: copies the app to %USERPROFILE%\keiba_app, installs libraries, trains the ability model (first time only),
rem registers a hidden start at every Windows logon, and starts the app now.
setlocal
for %%I in ("%~dp0..") do set "SRC=%%~fI"
set "DEST=%USERPROFILE%\keiba_app"
set "KDB=%USERPROFILE%\.keiba\db\keiba.db"
set "MODELS=%USERPROFILE%\.keiba\models"
set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "PYW="
for /f "delims=" %%i in ('where pythonw 2^>nul') do if not defined PYW set "PYW=%%i"
if not defined PYW (
  echo pythonw.exe was not found. Install Python and tick "Add python.exe to PATH".
  pause
  exit /b 1
)
echo [1/5] Stopping the running app if any ...
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*keiba_app*app.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"
echo [2/5] Copying the app to "%DEST%" ...
robocopy "%SRC%" "%DEST%" /E /XD .git data models __pycache__ /XF racing_app.db >nul
if errorlevel 8 (
  echo Copy failed.
  pause
  exit /b 1
)
echo [3/5] Installing the libraries, first time only ...
python -m pip install -q -r "%DEST%\requirements.txt"
echo [4/5] Preparing the ability model ...
if not exist "%KDB%" (
  echo   keiba.db was not found at %KDB%
  echo   Skipping. The simulation needs keiba.db and a trained model.
) else (
  dir /b "%MODELS%\keiba_stage12_*.joblib" >nul 2>&1
  if errorlevel 1 (
    echo   Training the ability model. This takes several minutes, please wait ...
    if not exist "%DEST%\data" mkdir "%DEST%\data"
    python "%DEST%\keiba\train.py" "%KDB%" > "%DEST%\data\train_log.txt" 2>&1
    if errorlevel 1 (
      echo   Training FAILED. See "%DEST%\data\train_log.txt"
    ) else (
      echo   Training finished.
    )
  ) else (
    echo   A trained model already exists. Skipping.
  )
)
echo [5/5] Registering the startup entry and starting the app ...
echo CreateObject("Wscript.Shell").Run """%PYW%"" ""%DEST%\app.py""", 0, False > "%STARTUP%\keiba_viewer.vbs"
powershell -NoProfile -Command "$d=[Environment]::GetFolderPath('Desktop'); Set-Content -Path (Join-Path $d 'keiba-viewer.url') -Value @('[InternetShortcut]','URL=http://localhost:5000')"
wscript "%STARTUP%\keiba_viewer.vbs"
echo.
echo Done. Open http://localhost:5000 - a shortcut keiba-viewer is on the Desktop.
echo The app now starts by itself when you log in to Windows.
echo To train the model again, delete the folder %MODELS% and run this file once more.
pause
