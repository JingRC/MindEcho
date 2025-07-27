@echo off
echo ========================================
echo 🎨 强制彩色渐变模式测试
echo ========================================
echo.
echo 修复内容:
echo   • 完全隐藏绿色背景线条
echo   • 强力清除所有旧的collections
echo   • 强制使用LineCollection彩虹渐变
echo   • 跨域测试数据 (C3-C6)
echo.
echo 预期效果:
echo   ✅ 0.8px超细彩虹渐变线条
echo   ✅ 仅前端一个高亮粒子
echo   ❌ 不应该有绿色粗线条
echo   🌈 颜色从蓝色渐变到红色
echo.
pause

cd /d "%~dp0"
python test_force_gradient.py

echo.
echo 测试完成！
echo 如果仍然看到绿色线条，请检查控制台输出
pause
