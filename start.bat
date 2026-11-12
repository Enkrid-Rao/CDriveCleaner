@echo off
chcp 65001 >nul
title CDriveCleaner
cd /d "%~dp0"

REM ============================================================
REM  CDriveCleaner v2 - source-mode launcher
REM  Requires Python 3.11+ with PySide6 installed.
REM ============================================================
where python >nul 2>nul
if errorlevel 1 (
    py -3 -m cdc
) else (
    python -m cdc
)
if errorlevel 1 (
    echo.
    echo Failed to start. Install dependencies with:
    echo     python -m pip install PySide6
    pause
)
