@echo off
cd /d "d:\-MindEcho-main"
echo 🚀 MindEcho 超低延迟监听优化测试
echo.
echo 🎯 本次优化内容：
echo   ✅ 缓冲区: 256样本 → 128样本 (减少50%%)
echo   ✅ 采样率: 48kHz → 96kHz (响应速度翻倍)
echo   ✅ 理论延迟: 5.33ms → 1.33ms (减少75%%)
echo   ✅ ASIO驱动: 专业级硬件加速
echo   ✅ 处理优化: 简化算法减少计算
echo   ✅ 实时监测: 处理时间+延迟统计
echo.
echo 🧪 测试目标：
echo   • 实现接近专业监听器的实时响应
echo   • 保持高音稳定性和电流音保护
echo   • 提供详细的性能监测信息
echo.
echo 💡 测试提示：
echo   - 连接耳机以获得最佳体验
echo   - 关闭其他音频应用程序
echo   - 观察控制台的延迟统计信息
echo.
echo 按任意键开始测试...
pause >nul
python test_ultra_low_latency.py
pause
