@echo off
rem Removes the startup entry and stops the running app. The copied folder %USERPROFILE%\keiba_app is kept.
del "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\keiba_viewer.vbs" 2>nul
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*keiba_app*app.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"
echo Autostart removed and the app stopped.
pause
