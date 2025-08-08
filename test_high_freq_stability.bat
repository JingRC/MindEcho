@echo off
echo 🎵 MindEcho 高频稳定性优化测试
echo.
echo 本次优化专门解决高音大音量时监听返回声音不稳定的问题
echo.
echo 🔧 主要改进：
echo   ✅ 高频内容智能识别（频谱分析）
echo   ✅ 分层稳定性处理（软限制器）
echo   ✅ 缓冲区优化（256样本块）
echo   ✅ DC偏移保护增强
echo.
echo 🎯 测试重点：
echo   1. 女高音(C5-C6)稳定性
echo   2. 男高音(C4-C5)音质
echo   3. 大音量时的抖动问题
echo   4. 音量梯度平滑过渡
echo.
echo 启动MindEcho进行测试...
cd /d "d:\-MindEcho-main"
python test_high_freq_optimization.py
pause
