@echo off
echo 🚀 MindEcho 增强型电流音检测系统 - 快速验证
echo ============================================================

echo 📋 检查Python环境...
python --version
if %errorlevel% neq 0 (
    echo ❌ Python未安装或未添加到PATH
    pause
    exit /b 1
)

echo 📦 检查依赖包...
python -c "import numpy, scipy; print('✅ 核心依赖包已安装')" 2>nul
if %errorlevel% neq 0 (
    echo ⚠️ 正在安装缺失的依赖包...
    pip install numpy scipy
)

echo 🧪 运行快速系统验证...
python quick_test_system.py

echo.
echo 🎯 如果测试通过，可以直接启动MindEcho:
echo    python src\gui\integrated_recording_interface.py
echo.
pause
