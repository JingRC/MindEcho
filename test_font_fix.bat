@echo off
cd /d "d:\​​MindEcho"
echo 🔤 测试中文字体显示修复...
echo.
echo 检查项目:
echo 1. matplotlib图表中的中文标题和轴标签
echo 2. PyQt界面中的中文控件标签  
echo 3. 彩色渐变模式和心电图模式切换
echo 4. 中文字体自动检测和配置
echo.
echo 测试开始...
python test_chinese_font.py
echo.
echo 🔤 中文字体测试完成!
pause
