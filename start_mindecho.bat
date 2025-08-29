@echo off
echo 启动 MindEcho (使用 Python 3.11)
echo ================================

REM 内置 ffmpeg：若存在 tools\ffmpeg\bin\ffmpeg.exe 则临时注入 PATH
set "FF_BIN=%~dp0tools\ffmpeg\bin"
if exist "%FF_BIN%\ffmpeg.exe" (
	set "PATH=%FF_BIN%;%PATH%"
	echo 已启用内置 ffmpeg: %FF_BIN%\ffmpeg.exe
)

REM 使用 Python 3.11 运行 MindEcho
C:\Users\admin\AppData\Local\Programs\Python\Python311\python.exe run_enhanced.py

pause
