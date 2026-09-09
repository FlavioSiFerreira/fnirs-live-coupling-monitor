@echo off
title fNIRS Monitor demo, no hardware needed
color 0B
cd /d "%~dp0"

echo.
echo   ==================================================
echo    fNIRS Monitor demo
echo    No sensor and no OpenSignals needed
echo   ==================================================

call "%~dp0_setup.bat"
if not defined PYEXE goto :end

echo.
echo   Step 1 of 2: writing a synthetic recording that starts well,
echo   loses contact, then recovers.
echo.
"%PYEXE%" -u fnirs_live_monitor.py --make-demo demo_recording.txt --demo-quality mixed
if errorlevel 1 goto :end

echo.
echo   Step 2 of 2: replaying it as if it were live.
echo   Watch the tier drop to POOR and come back.
echo.
"%PYEXE%" -u fnirs_live_monitor.py --replay demo_recording.txt

:end
echo.
echo   Press any key to close this window.
pause >nul
