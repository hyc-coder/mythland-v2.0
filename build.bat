@echo off
REM ============================================================
REM  Remote Control - One Click Build Script
REM  Double click this file to build exe files.
REM  Requires: Windows + Python 3.8 or newer
REM
REM  This file is plain ASCII with CRLF line endings on purpose.
REM  Do not save it as UTF-8 with BOM - cmd.exe cannot parse that.
REM ============================================================

cd /d "%~dp0"

echo.
echo ============================================================
echo   Remote Control Builder
echo ============================================================
echo.
echo Working folder: %CD%
echo.

REM ---- check python ----
python --version
if errorlevel 1 goto NOPYTHON

echo.
echo Using this Python:
python -c "import sys; print('  ' + sys.executable)"
echo.
echo If this is NOT the Python where you installed pillow/mss,
echo the build will fail. Install deps with the SAME python:
echo   python -m pip install pillow mss psutil pyautogui
echo.
echo [1/2] Checking dependencies and PyInstaller ...
echo [2/2] Building exe - this may take several minutes ...
echo.

python build.py
if errorlevel 1 goto BUILDFAIL

echo.
echo ============================================================
echo   BUILD SUCCESS
echo ============================================================
echo.
echo Output files are in the dist folder:
echo.
dir /b dist
echo.
echo   Teacher PC : controller.exe
echo   Student PC : agent.exe        (silent, no window)
echo   Debug      : agent-debug.exe  (with console, for logs)
echo.
pause
exit /b 0

:NOPYTHON
echo.
echo ============================================================
echo   ERROR: Python was not found.
echo ============================================================
echo.
echo Please install Python 3 and make sure the option
echo "Add Python to PATH" is checked during installation.
echo.
echo Download: https://www.python.org/downloads/
echo.
pause
exit /b 1

:BUILDFAIL
echo.
echo ============================================================
echo   ERROR: Build failed.
echo ============================================================
echo.
echo Please read the message above.
echo If a package is missing, run this first:
echo.
echo   python -m pip install pillow mss psutil pyautogui
echo.
pause
exit /b 1
