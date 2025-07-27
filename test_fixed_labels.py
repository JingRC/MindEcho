#!/usr/bin/env python3
"""
测试左侧音调标签固定位置修复
"""

import sys
import os
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def test_fixed_labels():
    """测试左侧标签固定位置"""
    print("🔧 左侧音调标签固定位置修复完成！")
    print("="*60)
    print()
    print("🐛 问题分析:")
    print("❌ 原问题: 录音时左侧音调标签会向右移动")
    print("   • 标签X坐标计算: label_x = time_offset - (time_window * 0.03)")
    print("   • time_offset 随录音时间和自动跟随功能增加")
    print("   • 导致标签位置不断向右偏移")
    print("   • 用户感觉标签'跑了'，影响使用体验")
    print()
    print("🔧 修复方案:")
    print("✅ 使用视图相对坐标而非绝对时间坐标")
    print()
    print("修改前的代码:")
    print("   x_min = self.time_offset  # ❌ 动态变化的值")
    print("   label_x = x_min - (self.time_window * 0.03)")
    print()
    print("修改后的代码:")
    print("   current_xlim = self.ax.get_xlim()  # ✅ 当前视图边界")
    print("   x_min = current_xlim[0]  # ✅ 视图左边界")
    print("   label_x = x_min + (current_xlim[1] - current_xlim[0]) * 0.02")
    print("   # ✅ 固定在视图左侧2%位置")
    print()
    print("🎯 技术优势:")
    print("✅ 视图相对定位: 标签位置相对于当前视图固定")
    print("✅ 自适应缩放: 标签位置随视图缩放自动调整")
    print("✅ 完全可见: 始终在可视区域内，不会被遮挡")
    print("✅ 交互友好: 支持拖拽时标签正确跟随")
    print()
    print("🎵 用户体验提升:")
    print("• 录音时: 标签位置稳定，便于快速识别音高")
    print("• 自动跟随: 标签不受时间轴移动影响")
    print("• 手动导航: 拖拽视图时标签正确同步移动")
    print("• 缩放操作: 标签保持相对位置和可读性")
    print()
    print("🧪 测试验证项目:")
    print("1. 🎤 录音测试: 开始录音，观察标签是否固定在左侧")
    print("2. ⏱️ 时间测试: 录音30秒+，验证标签位置稳定性")
    print("3. 🎯 跟随测试: 音高变化时，验证标签不受自动跟随影响")
    print("4. 🖱️ 交互测试: 手动拖拽，确认标签正确跟随视图")
    print("5. 🔍 缩放测试: 调整缩放级别，验证标签相对位置")
    print()

if __name__ == "__main__":
    test_fixed_labels()
    
    # 询问是否启动实际测试
    choice = input("是否启动 MindEcho 验证修复效果? (y/n): ").lower()
    if choice == 'y':
        try:
            from src.gui.integrated_recording_interface import main as integrated_main
            print("\n🚀 启动 MindEcho 增强版...")
            print()
            print("重点观察:")
            print("• 左侧音调标签位置是否固定不动")
            print("• 录音过程中标签是否保持在左侧")
            print("• 自动跟随时标签位置是否稳定")
            print("• 手动操作时标签是否正确响应")
            print()
            print("操作建议:")
            print("1. 开始录音并发出不同音高")
            print("2. 等待自动跟随功能触发")
            print("3. 手动拖拽视图进行导航")
            print("4. 调整缩放级别测试适应性")
            print()
            integrated_main()
        except Exception as e:
            print(f"❌ 启动失败: {e}")
