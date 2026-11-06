@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)
%PYTHON_EXE% -m m2.cli demo
if errorlevel 1 (
    echo Demo failed. See README.md for installation instructions.
    exit /b 1
)
endlocal
