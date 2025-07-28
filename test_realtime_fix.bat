@echo off
cd /d "d:\-MindEcho-main"
echo 🧪 测试自动启动实时分析修复
echo.
echo 🔧 主要修复：
echo   1. 音频回调函数不再依赖录音状态
echo   2. 界面启动后自动开始实时分析
echo   3. 优化音高检测阈值
echo   4. 增加详细调试信息
echo.
echo 🎯 预期看到：
echo   • "✅ 实时音高分析已启动"
echo   • "🔄 异步处理状态" 队列大小>0
echo   • "🎼 颤音检测器启动"
echo   • 音高检测信息，不再显示"静音中"
echo.
echo 🚀 启动测试...
echo.
python test_realtime_analysis.py
pause
