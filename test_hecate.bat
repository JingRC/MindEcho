@echo off
echo HECATE G4 Pro 设备连接测试工具
echo ================================
echo.
echo 正在启动HECATE设备测试...
echo.

cd /d "%~dp0"

REM 激活虚拟环境（如果存在）
if exist "venv\Scripts\activate.bat" (
    echo 激活虚拟环境...
    call venv\Scripts\activate.bat
)

REM 运行HECATE测试
python test_hecate_connection.py

echo.
echo 测试完成！
pause
