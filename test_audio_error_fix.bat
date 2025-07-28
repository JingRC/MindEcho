@echo off
echo ===============================================
echo 🔧 MindEcho 音频错误修复测试
echo ===============================================
echo.
echo 修复的问题:
echo 1. unsupported operand type^(s^) for -: 'float' and 'NoneType'
echo 2. wrapped C/C++ object of type IntegratedAudioProcessor has been deleted
echo.
echo 🚀 正在启动测试...
python test_audio_error_fix.py
echo.
echo ✅ 测试完成！
pause
