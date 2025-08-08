@echo off
echo 🚀 MindEcho 增强型电流音检测系统 - 启动测试
echo ============================================================

echo 📋 检查Python环境...
python --version
if %errorlevel% neq 0 (
    echo ❌ Python未安装或未添加到PATH
    pause
    exit /b 1
)

echo 📦 检查依赖包...
python -c "import numpy, scipy, sounddevice; print('✅ 核心依赖包已安装')"
if %errorlevel% neq 0 (
    echo ⚠️ 正在安装缺失的依赖包...
    pip install numpy scipy sounddevice
)

echo 🔧 创建音频处理目录...
if not exist "src\audio_processing" mkdir "src\audio_processing"

echo 🧪 运行集成测试...
python test_advanced_integration.py

if %errorlevel% equ 0 (
    echo.
    echo ✅ 测试完成！系统已准备就绪。
    echo 🎯 现在可以启动MindEcho进行音频监听了。
    echo.
    choice /c YN /m "是否启动MindEcho音频监听？"
    if errorlevel 2 goto end
    if errorlevel 1 goto start_mindecho
) else (
    echo.
    echo ❌ 测试失败，请检查错误信息。
    echo 💡 建议：
    echo    1. 确保所有依赖包已正确安装
    echo    2. 检查音频设备连接
    echo    3. 运行 pip install -r requirements.txt
)

goto end

:start_mindecho
echo 🎵 正在启动MindEcho音频监听...
if exist "start_mindecho.py" (
    python start_mindecho.py
) else if exist "src\gui\integrated_recording_interface.py" (
    python src\gui\integrated_recording_interface.py
) else (
    echo ❌ 找不到MindEcho启动文件
)

:end
echo.
echo 感谢使用MindEcho增强型电流音检测系统！
pause
