@echo off
chcp 65001 > nul
echo.
echo ==========================================
echo 🎵 MindEcho 大声唱歌与气泡音优化测试
echo ==========================================
echo.
echo 🎯 本次优化针对两个关键问题:
echo    1. 大声唱歌时监听电音问题
echo    2. 气泡音技巧被误判为电音问题
echo.
echo 📊 优化参数详情:
echo.
echo 🔧 电流音检测优化:
echo    • RMS阈值: 0.003 → 0.0008 (严格4倍)
echo    • 高频分析频段: 3/4 → 7/8 (更高频段)
echo    • 高频比例阈值: 85%% → 95%% (避免误判气泡音)
echo    • RMS确认阈值: 0.002 → 0.0005 (更严格)
echo.
echo 🔧 VRMS限制器优化:
echo    • 动态范围阈值: 70%% → 85%% (大声唱歌友好)
echo    • 静音检测阈值: 0.0005 → 0.0003 (更精确)
echo    • DC偏移阈值: 0.02 → 0.03 (更保守)
echo.
echo 🎤 测试建议:
echo    1. 尝试大声唱歌 - 确认不再有电音干扰
echo    2. 使用气泡音技巧 - 验证不被误判为电音
echo    3. 测试各种音量级别 - 确保监听质量
echo    4. 验证真实电流音仍能被正确检测
echo.
echo ✨ 预期效果:
echo    • 大声唱歌: 清晰监听，无电音干扰
echo    • 气泡音: 完整保护，不触发电流音检测
echo    • 抖音技巧: 音高变化正确识别
echo    • 真实电流音: 仍能精确检测和抑制
echo.
pause
echo.
echo 🚀 启动优化版监听测试...
python integrated_recording_interface.py
pause
