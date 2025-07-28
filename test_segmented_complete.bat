@echo off
echo ========================================
echo 🎵 测试断续音调曲线功能
echo ========================================
echo.
echo 显示修复内容...
python test_segmented_curves.py
echo.
echo ========================================
echo 🚀 启动MindEcho增强版测试
echo ========================================
echo.
echo 测试要点：
echo 1. 观察换气时曲线是否断开
echo 2. 检查日志中的"检测到换气段"消息
echo 3. 验证音调段独立绘制
echo.
echo 按任意键启动...
pause > nul
python run_enhanced.py
