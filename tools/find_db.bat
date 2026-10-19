@echo off
rem Lists large SQLite-like files (50MB+) on all drives into found_db.txt and opens it. Takes a few minutes.
echo Searching... please wait (a few minutes).
powershell -NoProfile -Command "$roots = (Get-PSDrive -PSProvider FileSystem).Root; Get-ChildItem -Path $roots -Recurse -Force -Include *.db,*.sqlite,*.sqlite3,*.db3 -ErrorAction SilentlyContinue | Where-Object { $_.Length -gt 50MB } | Sort-Object Length -Descending | ForEach-Object { '{0} MB   {1}' -f [int]($_.Length/1MB), $_.FullName }" > "%~dp0found_db.txt"
for %%A in ("%~dp0found_db.txt") do if %%~zA==0 echo (not found) > "%~dp0found_db.txt"
start notepad "%~dp0found_db.txt"
