@echo off
echo ========================================
echo 🎨 MindEcho 超细平滑彩色渐变测试
echo ========================================
echo.
echo 测试内容:
echo   • 超细线条 (0.8px linewidth)
echo   • 平滑插值 (SciPy cubic/linear)
echo   • 仅前端粒子效果
echo   • 颤音细节显示优化
echo.
echo 请观察改进效果:
echo   1. 线条是否足够细腻
echo   2. 颜色渐变是否平滑
echo   3. 是否只有前端单个粒子
echo   4. 颤音细节是否清晰可见
echo.
pause

cd /d "%~dp0"
python test_ultra_thin_gradient.py

echo.
echo 测试完成！按任意键退出...
pause
