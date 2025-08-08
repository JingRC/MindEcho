@echo off
echo ===============================================
echo   MindEcho APO多层音频监听测试
echo   基于HECATE G4 Pro驱动架构优化
echo ===============================================
echo.
echo 🎵 新功能特性:
echo   ✅ EFX层: 音频明亮化 + 人声清晰化
echo   ✅ MFX层: 智能音量控制 + 动态低音增强  
echo   ✅ SFX层: 噪音抑制 + 实时RAW模式
echo   ✅ 多算法电流音检测（大幅减少误判）
echo   ✅ VRMS限制器防止失真
echo   ✅ 128样本块专业驱动配置
echo.
echo 🔧 优化内容:
echo   • 电流音检测阈值: 0.1 → 2.0 (减少误判)
echo   • 多重检测算法: 高频变化+频域分析+稳定性检测
echo   • APO三层架构: 模拟专业音频驱动处理流程
echo   • 智能音量控制: 自适应增益调整
echo   • 延迟优化: 128样本块 + RAW模式
echo.
echo 正在启动测试...
echo.

cd /d "D:\-MindEcho-main"
call C:/Users/admin/anaconda3/envs/music_coach_env/Scripts/activate.bat
C:/Users/admin/anaconda3/envs/music_coach_env/python.exe d:/-MindEcho-main/src/gui/integrated_recording_interface.py

pause
