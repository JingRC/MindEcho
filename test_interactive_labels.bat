@echo off
cd /d "d:\​​MindEcho"
echo 🎨 测试交互式音调标注系统
echo.
echo 🎯 新功能特性:
echo   • 智能音高高亮: 当前音高金色高亮
echo   • 距离透明度: 根据音高距离调整透明度
echo   • 自动超时: 1秒无音高输入后恢复标准显示
echo   • 完整可见: 任何缩放下标签都完整显示
echo   • 渐变兼容: 不影响彩色渐变线条显示
echo.
echo 🚀 开始测试...
python test_interactive_labels.py
echo.
echo 🎨 交互式音调标注测试完成!
echo.
echo 💡 如果效果满意，可以启动增强版体验:
echo python run_enhanced.py
echo.
pause
