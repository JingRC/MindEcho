@echo off
chcp 65001 >nul
title MindEcho优化启动器

echo =========================================================
echo 🚀 MindEcho优化启动器
echo    专为HECATE G4 Pro音频设备优化
echo    192000Hz / 32样本 / 0.17ms超低延迟
echo =========================================================
echo.

REM 检查Python环境
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python未安装或不在PATH中
    echo 💡 请安装Python或激活虚拟环境
    pause
    exit /b 1
)

REM 激活conda环境（如果存在）
if exist "%CONDA_PREFIX%" (
    echo ✅ 检测到Conda环境: %CONDA_PREFIX%
) else (
    REM 尝试激活music_coach_env环境
    call conda activate music_coach_env 2>nul
    if errorlevel 1 (
        echo ⚠️ 未找到music_coach_env环境，使用系统Python
    ) else (
        echo ✅ 激活Conda环境: music_coach_env
    )
)

echo.
echo 🔄 启动MindEcho优化系统...
echo.

REM 运行优化启动器
python start_mindecho_optimized.py

echo.
echo 🏁 启动完成
pause
