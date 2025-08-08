@echo off
echo 🧪 启动音调线滚动修复测试
echo.
echo 测试说明：
echo 1. 界面启动后，点击 "开始录音"
echo 2. 等待8秒观察自动滚动开始
echo 3. 拖动右侧垂直滚动条（上下）
echo 4. 检查音调线是否立即重新显示（修复前会消失）
echo 5. 拖动下方水平滚动条（左右） 
echo 6. 检查音调线是否正常显示
echo 7. 点击 "清除" 按钮测试清除功能
echo 8. 点击 "重置" 按钮测试重置功能
echo.
echo ✅ 如果上述操作都正常，说明修复成功！
echo.
cd /d "d:\-MindEcho-main"
python test_scroll_fix.py
pause
