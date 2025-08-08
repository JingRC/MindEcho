@echo off
chcp 65001
echo 🎵 MindEcho HECATE G4 Pro风格监听测试
echo.
echo 🎯 本次升级特性:
echo    • 超低延迟: 64样本块 (理论1.33ms延迟)
echo    • 专业电流音检测: FFT频谱分析方式
echo    • 人声技巧保护: 气泡音/抖音不会被误判
echo    • VRMS限制器: 70%动态范围控制
echo    • ASIO驱动支持: 专业音频接口优化
echo    • 智能RMS门限: 只检测极弱信号的真实电流音
echo.
echo 🔧 核心改进:
echo    • RMS阈值: 0.003 (极低信号才检测)
echo    • 高频比例: 85% (更严格的电流音特征)
echo    • 警告频率: 2000帧 (大幅减少干扰)
echo    • 频谱分析: 避免误判人声颤音技巧
echo.
echo 🎵 预期效果:
echo    • 延迟: ~1.3ms (接近硬件极限)
echo    • 气泡音/抖音: 完全不受干扰
echo    • 真实电流音: 精确检测和处理
echo    • 音质: 专业级动态范围控制
echo.
echo 正在启动HECATE风格监听测试...
echo.

cd /d "%~dp0"
python src\gui\integrated_recording_interface.py

echo.
echo 测试完成。
pause
