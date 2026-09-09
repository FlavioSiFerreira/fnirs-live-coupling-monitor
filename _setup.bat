@echo off
rem Shared first-run setup, called by the three launcher files.
rem On success it sets PYEXE to the interpreter inside .venv.
rem It is safe to run again: after the first time it does nothing.

set "PYEXE="
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" goto :have_venv

echo.
echo   First run. Setting up.
echo   This takes a few minutes and happens only once.
echo.

set "BOOTPY="
py -3 --version >nul 2>&1
if not errorlevel 1 set "BOOTPY=py -3"
if defined BOOTPY goto :make_venv
python --version >nul 2>&1
if not errorlevel 1 set "BOOTPY=python"
if defined BOOTPY goto :make_venv
goto :no_python

:make_venv
echo   Creating a private Python environment in .venv
%BOOTPY% -m venv .venv
if errorlevel 1 goto :venv_failed
echo   Installing packages, please wait
".venv\Scripts\python.exe" -m pip install --upgrade pip --quiet --disable-pip-version-check
".venv\Scripts\python.exe" -m pip install -r requirements.txt --disable-pip-version-check
if errorlevel 1 goto :pip_failed
echo.
echo   Setup finished.
echo.

:have_venv
set "PYEXE=%~dp0.venv\Scripts\python.exe"
if exist "%~dp0models\chronos-t5-small\config.json" set "CHRONOS_LOCAL_DIR=%~dp0models\chronos-t5-small"
goto :eof

:no_python
echo.
echo   Python was not found on this computer.
echo.
echo     1. Open  https://www.python.org/downloads/
echo     2. Download Python 3.10 or newer.
echo     3. In the installer, TICK "Add python.exe to PATH".
echo     4. Run this file again.
echo.
goto :eof

:venv_failed
echo.
echo   Could not create the .venv folder.
echo   Copy this folder somewhere you can write to, for example your Desktop,
echo   and try again.
echo.
goto :eof

:pip_failed
echo.
echo   Could not install the packages.
echo   The most common cause is no internet connection on this computer.
echo   See the "No internet on the recording computer" section of README.md.
echo.
goto :eof
