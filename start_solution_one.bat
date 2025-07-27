@echo off
echo 🎨 启动 MindEcho 方案一：改进的彩色渐变可视化器
echo ================================================
echo.
echo 💡 这是专门解决彩色渐变显示问题的方案一
echo 📋 特点：
echo   • 解决 Matplotlib 3.10.1 兼容性问题
echo   • 5种渐变模式可选
echo   • 4个质量等级
echo   • 强制刷新功能
echo.
echo 🚀 正在启动...
echo.

cd /d "%~dp0"
python test_solution_one.py

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ❌ 启动失败，尝试通过主启动器...
    echo.
    python run_enhanced.py
)

echo.
echo 👋 程序已退出
pause
