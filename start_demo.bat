@echo off
REM ============================================================
REM  Remote Control - Local Demo Launcher
REM  Simulates 3 agents on ONE computer.
REM  For real deployment just double click controller.exe
REM  and agent.exe - no arguments needed.
REM
REM  Plain ASCII with CRLF on purpose.
REM  Do not save as UTF-8 with BOM - cmd.exe cannot parse that.
REM ============================================================

cd /d "%~dp0"

echo.
echo ============================================================
echo   Local Demo - 3 simulated agents on this computer
echo ============================================================
echo.
echo   For real use: double click controller.exe (teacher PC)
echo   and agent.exe (student PC). No arguments needed.
echo.
echo   This script is only for testing on ONE computer.
echo   Ports auto shift 9001 / 9002 / 9003, no conflict.
echo ============================================================
echo.
echo   The controller window will show the preview wall.
echo   Please wait 3-5 seconds for agents to appear.
echo   Agent windows show logs - do not close them.
echo.
echo ============================================================
echo.
pause

echo [1/4] Starting controller - preview wall ...
start "controller" python controller.py
timeout /t 2 >nul

echo [2/4] Starting agent - demo-01 ...
start "agent-01" python agent.py --name "demo-01"
timeout /t 1 >nul

echo [3/4] Starting agent - demo-02 ...
start "agent-02" python agent.py --name "demo-02"
timeout /t 1 >nul

echo [4/4] Starting agent - demo-03 ...
start "agent-03" python agent.py --name "demo-03"

echo.
echo All started. The controller window should show the wall.
echo If it is empty, wait 3-5 seconds for agents to go online.
echo.
pause
