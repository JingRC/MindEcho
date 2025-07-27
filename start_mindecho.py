#!/usr/bin/env python3
"""
MindEcho 启动指南
帮助用户选择正确的程序入口
"""

print("🎵 欢迎使用 MindEcho 智能音频分析系统 🎵")
print("=" * 60)
print()
print("请选择您要启动的程序:")
print()

print("🚀 【推荐】增强版 - 完整功能")
print("   文件: run_enhanced.py")
print("   功能: 实时音高检测 + 心电图式可视化 + 完整音域显示")
print("   命令: python run_enhanced.py")
print()

print("📱 标准版 - 基础录音")
print("   文件: src/gui/enhanced_main_window.py")
print("   功能: 基础录音 + 简单音高分析")
print("   命令: python src/gui/enhanced_main_window.py")
print()

print("🔬 测试程序")
print("   📊 性能分析: python performance_analysis.py")
print("   💓 心电图测试: python test_ecg_pitch_detection.py")
print("   🎙️ 录音测试: python test_recording.py")
print("   🔧 集成测试: python test_integration.py")
print()

print("💡 建议启动顺序:")
print("1. 首次使用: python run_enhanced.py")
print("2. 遇到问题: python test_recording.py (检查录音功能)")
print("3. 性能测试: python performance_analysis.py")
print()

choice = input("请输入您想启动的程序编号 (1-增强版, 2-测试录音, 3-性能分析): ").strip()

if choice == "1":
    print("\n🚀 启动增强版 MindEcho...")
    import subprocess
    import sys
    subprocess.run([sys.executable, "run_enhanced.py"])
elif choice == "2":
    print("\n🎙️ 启动录音测试...")
    import subprocess
    import sys
    subprocess.run([sys.executable, "test_recording.py"])
elif choice == "3":
    print("\n📊 启动性能分析...")
    import subprocess
    import sys
    subprocess.run([sys.executable, "performance_analysis.py"])
else:
    print("\n💡 手动启动命令:")
    print("  增强版: python run_enhanced.py")
    print("  录音测试: python test_recording.py")
    print("  性能分析: python performance_analysis.py")
