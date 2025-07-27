@echo off
echo ========================================
echo 🔍 彩色渐变问题诊断测试
echo ========================================
echo.
echo 测试步骤:
echo   1. 基础彩色渐变功能测试 (独立matplotlib)
echo   2. 集成界面调试测试 (查看错误信息)
echo   3. 问题诊断报告
echo.
pause

echo.
echo 🧪 第1步：测试基础彩色渐变功能...
echo ========================================
python test_basic_gradient.py

echo.
echo 🔍 第2步：集成界面调试测试...
echo ========================================
echo 请观察控制台输出中的错误信息...
python debug_gradient.py

echo.
echo 📋 测试完成！
echo.
echo 分析结果:
echo   • 如果第1步显示彩色线条 = 基础功能正常
echo   • 如果第2步有错误信息 = 集成问题
echo   • 请将控制台输出信息反馈给开发者
echo.
pause
