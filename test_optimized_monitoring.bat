@echo off
cd /d "%~dp0"
echo 🚀 启动 MindEcho 优化监听功能测试
echo.
echo ✨ 本次优化亮点:
echo    🔧 48kHz采样 + 128样本块 = 超低延迟（约2.7ms）
echo    🎯 IIR滤波器 + 智能降噪 = 高音质处理
echo    📊 实时延迟监测 + 性能统计 = 可视化优化效果
echo.
echo 🎧 请准备好耳机，点击界面的"开启监听"按钮开始测试
echo.
pause
python test_optimized_monitoring.py
pause
