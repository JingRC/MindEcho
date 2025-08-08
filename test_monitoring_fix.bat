@echo off
cd /d "d:\-MindEcho-main"
echo 🎧 MindEcho 监听功能大音量电流音修复测试
echo.
echo 🔧 修复内容：
echo   ✅ 分段式动态范围控制 - 90%%以下保持原音质
echo   ✅ 智能电流音检测 - 动态阈值，避免误判大音量
echo   ✅ 缓冲区优化 - 128样本块，平衡延迟和稳定性
echo   ✅ DC偏移处理优化 - 减少对音频的干扰
echo.
echo 🧪 测试重点：
echo   📢 大声说话/唱歌时是否还有电流音失真
echo   📢 各种人声技巧是否被正确处理
echo   📢 音质是否保持清晰自然
echo.
echo 🎯 使用说明：
echo   1. 程序启动后找到可视化器区域
echo   2. 点击 "开启监听" 按钮
echo   3. 进行各种音量测试
echo   4. 验证大音量时是否消除了电流音问题
echo.
python test_monitoring_fix.py
pause
