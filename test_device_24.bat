@echo off
echo HECATE G4 Pro 设备24专用测试
echo ===============================
echo.
echo 测试设备24的192kHz/32样本配置...
echo.

cd /d "%~dp0"

REM 激活虚拟环境（如果存在）
if exist "venv\Scripts\activate.bat" (
    echo 激活虚拟环境...
    call venv\Scripts\activate.bat
)

REM 运行设备24专用测试
python test_device_24.py

echo.
echo 测试完成！
pause
