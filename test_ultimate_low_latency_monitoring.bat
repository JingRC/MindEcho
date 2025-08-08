@echo off
cd /d "d:\-MindEcho-main"
echo 🚀 MindEcho 终极超低延迟监听测试
echo.
echo 🎯 本次超级优化内容：
echo   ✅ 采样率：48kHz → 96kHz (100%提升)
echo   ✅ 块大小：64 → 32样本 (50%减少)  
echo   ✅ 理论延迟：1.33ms → 0.33ms (75%降低)
echo   ✅ 大音量稳定性：动态压缩 + 削峰限制
echo   ✅ 驱动优化：ASIO → WaveOut → 兼容三级回退
echo.
echo 🧪 测试重点：
echo   1. 延迟是否达到 ^< 0.5ms
echo   2. 大声唱歌是否稳定无杂音
echo   3. 小声说话是否清晰可听
echo   4. 响应是否真正实时
echo.
echo 按任意键开始测试...
pause >nul

python test_ultimate_low_latency_monitoring.py

echo.
echo 🔄 测试完成！如需重新测试，请重新运行此文件。
pause
