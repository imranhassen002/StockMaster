@echo off
title StockMaster
rem Double-click this file to start StockMaster without opening VS Code.
cd /d "%~dp0"

rem Use "python" if it is on PATH, otherwise the Windows "py" launcher.
set "PY=python"
where python >nul 2>nul || set "PY=py"

rem Check that the required libraries are installed before starting.
%PY% -c "import tkinter, pandas, numpy, matplotlib, openpyxl" >nul 2>nul
if errorlevel 1 (
    echo StockMaster could not start.
    echo Python or one of the required libraries is missing.
    echo.
    echo Open a terminal in this folder and run:
    echo     python -m pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)

rem pythonw starts the app without leaving a black console window open.
start "" %PY%w main.py
