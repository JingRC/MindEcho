@echo off
title MindEcho LineCollection彩色渐变测试
color 0A
cls

echo.
echo ========================================
echo   MindEcho LineCollection彩色渐变测试
echo ========================================
echo.
echo 正在启动Matplotlib LineCollection测试...
echo.

cd /d "%~dp0"
python matplotlib_gradient_test.py

echo.
echo ========================================
echo     Matplotlib测试完成
echo ========================================
echo.
echo 如果看到了三种不同的彩色渐变效果：
echo   方法1: LineCollection - 最佳性能和效果
echo   方法2: 分段线条 - 兼容性好
echo   方法3: 散点组合 - 粒子效果
echo.
echo 现在启动完整的集成测试...
echo.
pause
cls

echo.
echo ========================================
echo      集成测试 - 彩色渐变vs心电图
echo ========================================
echo.
echo 正在启动主界面集成测试...
echo 请在界面中：
echo   1. 切换到彩色渐变模式
echo   2. 观察LineCollection真彩色效果
echo   3. 切换到心电图模式对比
echo.

python test_final_gradient.py

echo.
echo 测试完成！
pause
