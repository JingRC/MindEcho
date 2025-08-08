@echo off
echo 🎵 MindEcho 增强型电流音检测系统 - 启动器
echo ============================================================

echo 📋 检查Python环境...
python --version
if %errorlevel% neq 0 (
    echo ❌ Python未安装或未添加到PATH
    pause
    exit /b 1
)

echo 📦 检查必要依赖...
python -c "import PyQt6; print('✅ PyQt6已安装')" 2>nul
if %errorlevel% neq 0 (
    echo ⚠️ 正在安装PyQt6...
    pip install PyQt6
)

python -c "import numpy, scipy, sounddevice; print('✅ 音频处理依赖已安装')" 2>nul
if %errorlevel% neq 0 (
    echo ⚠️ 正在安装音频处理依赖...
    pip install numpy scipy sounddevice
)

echo 🚀 启动MindEcho增强型电流音检测系统...
python start_mindecho_enhanced.py

echo.
echo 感谢使用MindEcho！
pause
