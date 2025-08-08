@echo off
chcp 65001 > nul
title MindEcho设备选择功能测试

echo 🎧 MindEcho设备选择功能测试
echo =====================================

REM 检查Python环境
echo 📋 检查Python环境...
where python > nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ 没有找到Python，请确保Python已安装并在PATH中
    echo 💡 尝试使用conda环境...
    if exist "C:\Users\admin\anaconda3\envs\music_coach_env\python.exe" (
        echo ✅ 找到conda环境，使用music_coach_env
        set PYTHON_CMD=C:\Users\admin\anaconda3\envs\music_coach_env\python.exe
    ) else (
        echo ❌ 没有找到可用的Python环境
        pause
        exit /b 1
    )
) else (
    set PYTHON_CMD=python
)

echo ✅ 使用Python: %PYTHON_CMD%

REM 检查必要的依赖
echo 📦 检查依赖包...
%PYTHON_CMD% -c "import sounddevice, PyQt6, numpy" 2>nul
if %errorlevel% neq 0 (
    echo ❌ 缺少必要的依赖包
    echo 💡 请运行以下命令安装:
    echo    pip install sounddevice PyQt6 numpy
    pause
    exit /b 1
)

echo ✅ 依赖包检查完成

REM 启动测试
echo 🚀 启动MindEcho设备选择功能测试...
echo.
echo 📝 功能说明:
echo    右键点击"开启监听"按钮 → 选择设备 → 测试监听
echo.

%PYTHON_CMD% test_device_selector.py

REM 检查运行结果
if %errorlevel% neq 0 (
    echo.
    echo ❌ 测试运行出错
    echo 💡 请检查错误信息并重试
) else (
    echo.
    echo ✅ 测试完成
)

pause
