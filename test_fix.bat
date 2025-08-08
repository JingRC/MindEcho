@echo off
echo 🔧 MindEcho 电流音检测器修复验证
echo ============================================================

echo 📋 检查Python环境...
python --version
if %errorlevel% neq 0 (
    echo ❌ Python未安装或未添加到PATH
    pause
    exit /b 1
)

echo 🧪 运行电流音检测器修复验证...
python test_electric_noise_fix.py

echo.
echo 🎯 如果测试通过，现在可以正常启动MindEcho了！
echo    建议使用: start_enhanced.bat
echo.
pause
