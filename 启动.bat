@echo off
chcp 65001 >nul
title CDriveCleaner
cd /d "%~dp0"

REM 优先使用打包好的 exe
if exist "dist\CDriveCleaner.exe" (
    start "" "dist\CDriveCleaner.exe"
    exit /b 0
)

REM 没有 exe 则用源码模式启动 GUI（需要 Python + PySide6）
echo ========================================
echo   CDriveCleaner - 桌面 GUI 启动中...
echo ========================================
echo.
echo 未找到打包 exe，使用源码模式启动。
echo 需要 Python 3.11+ 和 PySide6 (pip install PySide6)
echo.

python -m src

if errorlevel 1 (
    echo.
    echo 启动失败，请检查 Python 环境和依赖
    pause
)
