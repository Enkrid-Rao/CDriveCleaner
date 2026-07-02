@echo off
chcp 65001 >nul
title DiskJunction
echo ========================================
echo   DiskJunction - 正在启动...
echo ========================================
echo.
echo 启动后请在浏览器访问: http://localhost:8765
echo 按 Ctrl+C 关闭服务
echo.

cd /d "%~dp0"
python -m src

pause
