@echo off
title fNIRS Monitor self test
color 0B
cd /d "%~dp0"

echo.
echo   ==================================================
echo    fNIRS Monitor self test
echo    Checks the whole chain end to end, no hardware
echo   ==================================================

call "%~dp0_setup.bat"
if not defined PYEXE goto :end

echo.
"%PYEXE%" -u fnirs_live_monitor.py --selftest

:end
echo.
echo   Press any key to close this window.
pause >nul
