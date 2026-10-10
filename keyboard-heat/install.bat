@echo off
setlocal
cd /d "%~dp0"

rem ===========================================================
rem  Keyboard Heat Monitor - runtime setup (ASCII only, see run.bat)
rem
rem  Creates the isolated runtime .pyenv and installs pynput.
rem  Only ever creates files -- it deletes nothing.
rem ===========================================================

set "VENV=%~dp0.pyenv"

set "SYSPY=%LOCALAPPDATA%\Python\pythoncore-3.12-64\python.exe"
if not exist "%SYSPY%" set "SYSPY=%LOCALAPPDATA%\Python\pythoncore-3.14-64\python.exe"
if not exist "%SYSPY%" set "SYSPY=python"

echo ============================================
echo  Keyboard Heat Monitor - runtime setup
echo ============================================
echo.

if not exist "%VENV%\Scripts\python.exe" (
    echo [1/2] Creating runtime .pyenv with:
    echo        %SYSPY%
    "%SYSPY%" -m venv "%VENV%"
) else (
    echo [1/2] Runtime already exists, reusing it
)

echo [2/3] Installing pynput
"%VENV%\Scripts\python.exe" -m pip install --disable-pip-version-check pynput

rem Pillow is optional: only needed when overlay.log_image points at a
rem bitmap log pile (config.json). Without it the code-drawn logs are used.
echo [3/3] Installing pillow (optional, for bitmap log pile)
"%VENV%\Scripts\python.exe" -m pip install --disable-pip-version-check pillow

echo.
echo Verifying:
"%VENV%\Scripts\python.exe" -c "import pynput, tkinter; print('runtime OK  pynput + tkinter', tkinter.TkVersion)"
echo.
echo Done. Double-click run.bat to start.
echo.
pause
