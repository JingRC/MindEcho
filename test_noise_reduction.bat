@echo off
echo 🎵 MindEcho 降噪功能快速测试
echo ================================

echo 1. 启动降噪测试...
python test_noise_reduction.py

echo.
echo 2. 启动增强版MindEcho（含降噪功能）...
python run_enhanced.py

pause
