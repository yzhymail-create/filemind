@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

rem 使用 pythonw.exe 启动，不显示命令行窗口
set PYW=
pythonw --version >nul 2>nul
if !errorlevel!==0 (
  set PYW=pythonw
  goto found_python
)
py -3w --version >nul 2>nul
if !errorlevel!==0 (
  set PYW=py -3w
  goto found_python
)

rem 如果找不到 pythonw，回退到 python
set PYW=python
python --version >nul 2>nul
if !errorlevel!==0 goto found_python

goto no_python

:found_python
set DB=%~dp0data\filemind.sqlite
!PYW! -m filemind.main gui --db "!DB!"
exit /b 0

:no_python
msg * "Python not found. Please install Python from https://www.python.org/downloads/"
exit /b 1
