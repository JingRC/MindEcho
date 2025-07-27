#!/usr/bin/env python3
"""
测试多行状态显示功能
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

def main():
    print("📊 多行状态显示功能测试")
    print("="*50)
    print()
    print("界面改进:")
    print("  ✅ 状态信息分成两行显示，更清晰易读")
    print("  ✅ 第一行：基本信息（中心、时间、缩放、范围）")
    print("  ✅ 第二行：模式和数据信息（标注、跟随、数据统计）")
    print("  ✅ 使用较小字体节省空间")
    print("  ✅ 保持统一的视觉风格")
    print()
    print("显示内容:")
    print("  第一行示例：中心: C4 | 时间: 实时 | 缩放: 1.0x | 范围: 3.0八度")
    print("  第二行示例：标注: 智能 | 跟随: 自动跟随 | 数据: 150点(7.8%)")
    print()
    print("优势:")
    print("  • 信息更有条理，不再拥挤在一行")
    print("  • 相关信息分组显示，便于快速查找")
    print("  • 界面更整洁，提高可读性")
    print("  • 保留所有原有功能信息")
    print()
    print("测试方法:")
    print("  1. 启动程序")
    print("  2. 观察控制面板右侧的状态显示区域")
    print("  3. 开始录音或分析，观察状态信息实时更新")
    print("  4. 调整缩放、时间等参数，观察第一行变化")
    print("  5. 切换标注模式、跟随模式，观察第二行变化")
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
