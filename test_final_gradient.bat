@echo off
cd /d "d:\​​MindEcho"
echo 🎨 测试彩色渐变保持功能...
echo.
echo 请按以下步骤测试：
echo 1. 程序启动后，确认显示"模式: 彩色渐变"
echo 2. 开始录音或播放音频
echo 3. 观察是否出现彩色渐变线条
echo 4. 调整缩放级别（应该保持彩色渐变）
echo 5. 调整时间窗口（应该保持彩色渐变）
echo.
echo 如果看到彩色渐变线条并且在各种操作中保持，说明修复成功！
echo.
python run_enhanced.py
pause
