@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
cd /d "%~dp0"

echo ============================================================
echo  FileMind - Local File Memory and Version Manager
echo ============================================================
echo.

rem Find Python
set PY=
python --version >nul 2>nul
if !errorlevel!==0 (
  set PY=python
  goto found_python
)
py -3 --version >nul 2>nul
if !errorlevel!==0 (
  set PY=py -3
  goto found_python
)
goto no_python

:found_python
echo Python: !PY!
!PY! --version
echo.

echo [1/2] Installing dependencies...
!PY! -m pip install --user -q -r requirements.txt
if !errorlevel! neq 0 (
  echo [Error] pip install failed
  pause
  exit /b 1
)

set DB=%~dp0data\filemind.sqlite

echo [2/2] Starting FileMind GUI...
echo.
echo ============================================================
echo  FileMind Desktop App
echo  Close the window to exit
echo ============================================================
echo.

!PY! -m filemind.main gui --db "!DB!"
echo.
echo FileMind exited.
pause
exit /b 0

:no_python
echo [Error] Python not found
echo Install from https://www.python.org/downloads/
echo Check "Add python.exe to PATH"
start https://www.python.org/downloads/
pause
exit /b 1
