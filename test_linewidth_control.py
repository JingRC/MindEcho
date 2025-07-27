#!/usr/bin/env python3
"""
测试可调节线条粗细功能
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

def main():
    print("🖊️ 可调节线条粗细功能测试")
    print("="*50)
    print()
    print("新增功能:")
    print("  ✅ 线条粗细下拉菜单（8个预设值）")
    print("  ✅ 自定义线条粗细滑块（0.1px-5.0px）")
    print("  ✅ 实时预览和应用线条粗细")
    print("  ✅ 智能显示/隐藏自定义控件")
    print()
    print("预设值:")
    print("  • 0.5px 极细 - 适合精细分析")
    print("  • 0.6px 超细 - 默认心电图模式")
    print("  • 0.8px 细线 - 清晰可见")
    print("  • 1.0px 标准 - 常规使用")
    print("  • 1.5px 中等 - 中等粗细")
    print("  • 2.0px 粗线 - 突出显示")
    print("  • 2.5px 很粗 - 演示用")
    print("  • 3.0px 极粗 - 最粗选项")
    print("  • 自定义... - 滑块精确调节")
    print()
    print("使用方法:")
    print("  1. 在'线条粗细'下拉菜单中选择预设值")
    print("  2. 选择'自定义...'可使用滑块精确调节")
    print("  3. 线条粗细会实时应用到当前显示")
    print("  4. 控制台会显示当前线条粗细设置")
    print()
    print("测试步骤:")
    print("  1. 启动程序，选择'心电图模式'")
    print("  2. 开始录音或分析")
    print("  3. 在线条粗细菜单中尝试不同选项")
    print("  4. 选择'自定义...'测试滑块功能")
    print("  5. 观察线条粗细实时变化")
    print()
    
    try:
        from src.gui.integrated_recording_interface import main as integrated_main
        print("启动增强版界面...")
        integrated_main()
    except Exception as e:
        print(f"❌ 启动失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
