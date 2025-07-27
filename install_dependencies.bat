@echo off
echo ================================
echo MindEcho 依赖安装脚本
echo ================================
echo.

echo 正在检查Python环境...
python --version
if %errorlevel% neq 0 (
    echo 错误: 未找到Python环境，请先安装Python
    pause
    exit /b 1
)

echo.
echo 正在安装必要的依赖包...
echo.

echo 1. 安装音频处理库...
pip install sounddevice numpy scipy
if %errorlevel% neq 0 (
    echo 警告: 音频处理库安装可能有问题
)

echo.
echo 2. 安装GUI库（可选）...
pip install PyQt5
if %errorlevel% neq 0 (
    echo 注意: PyQt5安装失败，将使用tkinter作为备选方案
)

echo.
echo 3. 安装数据处理库（可选）...
pip install pandas matplotlib
if %errorlevel% neq 0 (
    echo 注意: 数据处理库安装可能有问题，但不影响基本功能
)

echo.
echo ================================
echo 安装完成！
echo ================================
echo.
echo 现在您可以运行以下命令启动MindEcho:
echo   python run_mindecho.py
echo.
echo 或者直接双击 run_mindecho.py 文件
echo.

pause
