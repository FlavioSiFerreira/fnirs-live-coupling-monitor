@echo off
rem Shared first-run setup, called by the three launcher files.
rem On success it sets PYEXE to the interpreter inside .venv.
rem It is safe to run again: after a finished setup it does nothing, and after
rem an interrupted one it finishes the job instead of leaving a broken folder.

set "PYEXE="
cd /d "%~dp0"

rem An offline machine can be given a wheels folder instead of the internet.
set "PIPSRC="
if exist "wheels\*.whl" set "PIPSRC=--no-index --find-links wheels"

if not exist ".venv\Scripts\python.exe" goto :make_venv
if exist ".venv\.setup-complete" goto :have_venv
echo.
echo   The last setup did not finish. Completing it now.
echo.
goto :install

:make_venv
echo.
echo   First run. Setting up.
echo   This takes a few minutes and happens only once.
echo.

set "BOOTPY="
py -3 --version >nul 2>&1
if not errorlevel 1 set "BOOTPY=py -3"
if defined BOOTPY goto :create
python --version >nul 2>&1
if not errorlevel 1 set "BOOTPY=python"
if defined BOOTPY goto :create
goto :no_python

:create
echo   Creating a private Python environment in .venv
%BOOTPY% -m venv .venv
if errorlevel 1 goto :venv_failed

:install
echo   Installing packages, please wait
if defined PIPSRC goto :install_requirements
".venv\Scripts\python.exe" -m pip install --upgrade pip --quiet --disable-pip-version-check

:install_requirements
".venv\Scripts\python.exe" -m pip install -r requirements.txt --disable-pip-version-check %PIPSRC%
if errorlevel 1 goto :pip_failed
".venv\Scripts\python.exe" -c "import numpy, scipy, torch, chronos" >nul 2>&1
if errorlevel 1 goto :verify_failed
echo setup complete> ".venv\.setup-complete"
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
echo   The usual cause is no internet connection on this computer. See the
echo   "No internet on the recording computer" section of README.md for the
echo   offline route, which uses a wheels folder.
echo   Nothing is broken: run this file again once the connection is back and
echo   it will pick up where it stopped.
echo.
goto :eof

:verify_failed
echo.
echo   The packages installed but could not be imported.
echo   Delete the .venv folder and run this file again for a clean build.
echo.
goto :eof
