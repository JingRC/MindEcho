@echo off
chcp 65001 >nul
title MindEcho Launcher
cd /d "%~dp0"

echo ==============================================
echo MindEcho Unified Launcher
echo This is the only supported launcher.
echo ==============================================
echo.

set "FF_BIN=%~dp0tools\ffmpeg\bin"
if exist "%FF_BIN%\ffmpeg.exe" (
    set "PATH=%FF_BIN%;%PATH%"
    echo Built-in ffmpeg enabled: %FF_BIN%\ffmpeg.exe
)

python --version >nul 2>&1
if errorlevel 1 (
    echo Python was not found. Please install it or activate your environment.
    pause
    exit /b 1
)

echo Starting MindEcho...
python main.py
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
    echo.
    echo Launch failed. Exit code: %EXIT_CODE%
    pause
    exit /b %EXIT_CODE%
)

echo.
echo Program exited.
pause
