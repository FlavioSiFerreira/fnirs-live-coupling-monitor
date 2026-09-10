@echo off
title fNIRS Live Coupling Quality Monitor
color 0B
cd /d "%~dp0"

echo.
echo   ==================================================
echo    fNIRS Live Coupling Quality Monitor
echo    Chronos T5 Small, zero shot, no training
echo   ==================================================

call "%~dp0_setup.bat"
if not defined PYEXE goto :end

echo.
echo   Start recording in OpenSignals once the monitor says it is watching.
echo   Press Ctrl+C to stop.
echo.

"%PYEXE%" -u fnirs_live_monitor.py %*

:end
echo.
echo   Press any key to close this window.
pause >nul
