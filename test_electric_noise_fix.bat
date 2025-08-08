@echo off
chcp 65001
echo 🔧 MindEcho 电流音修复版测试
echo.
echo 🎯 本次修复重点:
echo    • 电流音检测阈值: 3.0 → 4.5 (减少误检)
echo    • RMS阈值: 0.02 → 0.015 (更精确检测)
echo    • 警告频率: 500帧 → 800帧 (减少干扰)
echo    • 音频处理: 安全复制，避免直接引用
echo    • DC偏移阈值: 0.005 → 0.01 (更保守)
echo    • 限幅算法: 改为温和限幅方式
echo    • 移除可能引入噪音的缓冲优化
echo.
echo 🔧 预期效果:
echo    • 大幅减少误检导致的"电流音"增加
echo    • 保持低延迟性能 (~3-5ms)
echo    • 只在真实电流音时静音处理
echo.
echo 正在启动修复版测试...
echo.

cd /d "%~dp0"
python src\gui\integrated_recording_interface.py

echo.
echo 测试完成。
pause
