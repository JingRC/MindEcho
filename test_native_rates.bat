@echo off
echo HECATE G4 Pro 原生采样率测试
echo ================================
echo.
echo 正在测试HECATE设备支持的所有采样率...
echo.

cd /d "%~dp0"

REM 激活虚拟环境（如果存在）
if exist "venv\Scripts\activate.bat" (
    echo 激活虚拟环境...
    call venv\Scripts\activate.bat
)

REM 运行原生采样率测试
python test_hecate_native_rates.py

echo.
echo 测试完成！
pause
