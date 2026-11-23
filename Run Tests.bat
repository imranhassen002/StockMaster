@echo off
title StockMaster - Running tests
cd /d "%~dp0"
set "PY=python"
where python >nul 2>nul || set "PY=py"
echo Running all StockMaster tests. App windows may open and close by themselves.
echo Please do not click anything until it finishes.
echo.
%PY% -m unittest discover -s tests -v
echo.
if errorlevel 1 (
    echo ==========================================
    echo   SOME TESTS FAILED - send a screenshot
    echo ==========================================
) else (
    echo ==========================================
    echo   ALL TESTS PASSED
    echo ==========================================
)
pause
