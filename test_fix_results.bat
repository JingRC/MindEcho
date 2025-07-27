@echo off
cd /d "d:\​​MindEcho"
echo 🔧 测试修复效果：音调标签显示 + 长时间录制
echo.
echo 🎯 修复内容：
echo 1. 音调标签位置自适应（解决左边显示不全）
echo 2. 数据缓冲区扩大到5分钟（解决录制中断）
echo 3. 彩色渐变清理优化（解决渐变消失）
echo 4. 缓冲区使用率监控（防止数据丢失）
echo.
echo 🧪 测试将验证：
echo   ✅ 彩色渐变模式音调标签完整显示
echo   ✅ 长时间录制不会中断渐变显示
echo   ✅ 不同缩放级别下标签正常
echo   ✅ 数据缓冲区状态正常显示
echo.
echo 测试开始...
python test_recording_fixes.py
echo.
echo 🔧 修复测试完成!
pause
