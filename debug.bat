@echo off
setlocal
cd /d "%~dp0"
set "EIDOLARCH_DEBUG_STARTUP=1"
set "PYTHONPROFILEIMPORTTIME=1"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0bootstrap.ps1" -DebugStartup
set "RC=%ERRORLEVEL%"
echo.
echo Startup log: %~dp0data\startup-debug.log
pause
exit /b %RC%
