@echo off
echo ===============================================
echo   MindEcho 极简音频监听测试
echo   专注消除电流音问题
echo ===============================================
echo.
echo 🎯 极简优化策略:
echo   ✅ 简化音频处理：移除所有复杂的APO多层架构
echo   ✅ 降低采样率：48kHz → 44.1kHz（减少高频噪声）
echo   ✅ 增大块大小：128 → 512样本（减少处理频率）
echo   ✅ 高延迟模式：减少音频驱动压力
echo   ✅ 电流音检测阈值：提高到5.0（只检测明显异常）
echo   ✅ 直通处理：几乎不做任何音频处理
echo.
echo 🔧 关键改进:
echo   • 电流音检测极简化：只用一个简单算法
echo   • 处理频率大幅减少：每1000次才输出一次警告
echo   • 音频处理最小化：只做基本直流偏移去除
echo   • 参数保守化：44.1kHz + 512样本 + 高延迟
echo.
echo 测试重点:
echo   1. 电流音是否明显减少
echo   2. 音质是否更加纯净
echo   3. 可通过界面关闭电流音检测
echo.
echo 正在启动极简版测试...
echo.

cd /d "D:\-MindEcho-main"
call C:/Users/admin/anaconda3/envs/music_coach_env/Scripts/activate.bat
C:/Users/admin/anaconda3/envs/music_coach_env/python.exe d:/-MindEcho-main/src/gui/integrated_recording_interface.py

pause
