@echo off
chcp 65001
echo 🚀 MindEcho 低延迟音频监听测试
echo.
echo 🎯 本次优化特性:
echo    • 48kHz 高质量采样率
echo    • 128样本块 (超低延迟 ~2.7ms)
echo    • 优化电流音检测算法
echo    • 快速音频处理通路
echo    • 智能DC偏移去除
echo.
echo 🔧 预期延迟: 约3-5ms (理论最小2.7ms)
echo ⚡ 电流音保护: 启用 (平衡敏感度)
echo.
echo 正在启动低延迟监听测试...
echo.

cd /d "%~dp0"
python src\gui\integrated_recording_interface.py

echo.
echo 测试完成。
pause
