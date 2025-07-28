@echo off
echo 🎵 MindEcho 音高检测修复验证测试
echo ========================================

echo 正在运行修复验证测试...
python test_pitch_detection_fix.py

echo.
echo 测试完成！现在启动MindEcho进行实际测试...
echo.
pause

echo 启动MindEcho增强版...
python run_enhanced.py
