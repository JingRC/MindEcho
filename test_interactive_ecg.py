#!/usr/bin/env python3
"""
测试心电图交互功能
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

def main():
    print("🎵 启动心电图交互功能测试版...")
    print()
    print("✨ 新增交互功能:")
    print("  🖱️  鼠标拖拽: 上下拖拽调整音高范围，左右拖拽查看历史数据")
    print("  🔍 滚轮缩放: 滚轮上下调整音高显示的缩放级别")
    print("  📊 详细音名: 显示C4, D4, E4等详细音名标注")
    print("  ⏰ 历史数据: 支持60秒历史数据查看")
    print("  🎯 重置视图: 一键回到默认视图（C4中心）")
    print("  📈 状态显示: 实时显示当前音高中心、时间偏移、缩放等信息")
    print()
    print("🎹 音高范围:")
    print("  • C0 到 C8 完整音域支持")
    print("  • 十二平均律: C, C#, D, D#, E, F, F#, G, G#, A, A#, B")
    print("  • 八度分组示例: C4-B4 = [C4, D4, E4, F4, G4, A4, B4]")
    print("  • 中央C = C4 (261.63Hz)，标准音 A4 = 440Hz")
    print()
    print("🔧 操作说明:")
    print("  • 上下拖拽: 调整显示的音高范围")
    print("  • 左右拖拽: 查看历史录音数据")
    print("  • 滚轮: 缩放音高显示精度")
    print("  • 重置视图按钮: 回到C4为中心的默认视图")
    print("  • 状态栏: 显示当前视图中心、时间偏移和缩放信息")
    print()
    print("🚀 启动集成界面...")
    
    try:
        from src.gui.integrated_recording_interface import main as integrated_main
        integrated_main()
    except Exception as e:
        print(f"❌ 启动失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
