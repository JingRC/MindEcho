@echo off
title MindEcho 彩色渐变测试
color 0A
cls

echo.
echo ========================================
echo      MindEcho 彩色渐变效果验证
echo ========================================
echo.
echo 即将启动彩色渐变测试程序...
echo.
echo 验证内容:
echo   [1] 彩色渐变模式 - HSV彩虹效果
echo   [2] 心电图模式 - 1.0px细线条  
echo   [3] 颤音细节显示清晰度
echo.
echo 程序将自动加载测试数据并演示效果
echo.
pause

cd /d "%~dp0"

echo.
echo 正在启动测试程序...
python test_rainbow_gradient.py

echo.
echo ========================================
echo            测试完成
echo ========================================
echo.
echo 如果效果满意，您可以通过以下方式使用:
echo   方法1: python run_enhanced.py (选择1-增强版)
echo   方法2: python run_enhanced.py (选择4-渐变测试)
echo.
pause
