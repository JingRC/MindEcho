@echo off
echo ===============================================
echo MindEcho 快速测试和启动脚本
echo Python 3.12.11 + PyQt6 版本
echo ===============================================
echo.

echo 1. 测试录音功能
echo 2. 启动GUI应用
echo 3. 安装缺失依赖
echo 4. 退出
echo.

set /p choice="请选择 (1-4): "

if "%choice%"=="1" (
    echo.
    echo 启动录音功能测试...
    python test_recording.py
    pause
) else if "%choice%"=="2" (
    echo.
    echo 启动MindEcho GUI应用...
    python run_mindecho.py
    pause
) else if "%choice%"=="3" (
    echo.
    echo 安装缺失依赖...
    echo 检查sounddevice...
    pip install sounddevice
    echo.
    echo 如果您使用的是Python 3.12+，建议使用PyQt6
    pip install PyQt6
    echo.
    echo 依赖安装完成！
    pause
) else if "%choice%"=="4" (
    echo 退出
    exit
) else (
    echo 无效选择
    pause
)

echo.
echo 按任意键退出...
pause > nul
