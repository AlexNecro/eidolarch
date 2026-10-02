@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0bootstrap.ps1" -Repair
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" (
  echo.
  echo Eidolarch repair failed.
  pause
)
exit /b %RC%
