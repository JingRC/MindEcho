@echo off
echo ========================================
echo 🔧 测试音高检测算法修复
echo ========================================
echo.
echo 运行算法修复验证测试...
python test_algorithm_fix.py
echo.
echo ========================================
echo 🎵 启动真实音频测试
echo ========================================
echo.
echo 按任意键启动MindEcho实时测试...
pause > nul
python start_mindecho.py
