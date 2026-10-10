@echo off
setlocal
cd /d "%~dp0"

rem ===========================================================
rem  Keyboard Heat Monitor - launcher
rem
rem  Dependency probing moved into main.py. Previously this bat
rem  spawned 2-3 cold python.exe processes just to "import pynput"
rem  / "import PIL" / "import PyQt6" on EVERY launch -- each cold
rem  python start costs ~0.3-0.8s on Windows, so a double-click
rem  silently waited ~1s before the window appeared. Now run.bat
rem  starts the real process once; main.py checks/falls back.
rem
rem  Every step still appends to _launch.log for post-hoc diagnosis.
rem ===========================================================

set "LOG=%~dp0_launch.log"
set "VENV=%~dp0.pyenv"
set "PYW=%VENV%\Scripts\pythonw.exe"

echo [%date% %time%] run.bat start > "%LOG%"

if not exist "%PYW%" goto :no_runtime
echo   runtime OK >> "%LOG%"

start "" "%PYW%" "%~dp0main.py" %*
echo   launched >> "%LOG%"
exit /b 0

:no_runtime
echo   runtime MISSING >> "%LOG%"
echo.
echo Runtime not found:
echo   %VENV%
echo.
echo Run install.bat first.
echo.
pause
exit /b 1
